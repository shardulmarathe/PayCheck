import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { RefObject } from "react";
import {
  BoxGeometry,
  BufferGeometry,
  CanvasTexture,
  EdgesGeometry,
  Float32BufferAttribute,
  LineBasicMaterial,
  LinearFilter,
  MathUtils,
  MeshBasicMaterial,
  MeshStandardMaterial,
  NoToneMapping,
  PlaneGeometry,
  SRGBColorSpace,
  type Group,
  type Material,
} from "three";
import { easeOut } from "../lib/ease";
import { formatLatencyCount } from "../lib/format";

export interface KioskScreen {
  url: string;
  lines: { label: string; value: string; trick?: boolean }[];
  latency: number | null;
  example: boolean;
}

const EASE_CSS = "cubic-bezier(0.22, 1, 0.36, 1)";

function drawScreen(
  canvas: HTMLCanvasElement,
  screen: KioskScreen,
  bracket: number,
  settle: number,
  glow: number,
  count: number,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#0A0C0F";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#232932";
  ctx.lineWidth = 2;
  ctx.strokeRect(12, 12, w - 24, h - 24);

  const pad = 56;
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#9AA3AE";
  ctx.font = "400 40px 'IBM Plex Mono', monospace";
  ctx.textAlign = "left";
  ctx.fillText(screen.url, pad, 96);
  ctx.fillStyle = "#232932";
  ctx.fillRect(pad, 128, w - pad * 2, 3);

  const trickIndex = Math.max(0, screen.lines.findIndex((line) => line.trick));
  screen.lines.forEach((line, index) => {
    const y = 230 + index * 108;
    const color = line.trick ? "#EEF1F5" : "#9AA3AE";
    ctx.fillStyle = color;
    ctx.font = "400 52px 'IBM Plex Sans', sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(line.label, pad, y);
    ctx.font = "400 52px 'IBM Plex Mono', monospace";
    ctx.textAlign = "right";
    ctx.fillText(line.value, w - pad, y);
    if (line.trick && bracket > 0.02) {
      const red = [255, 69, 58];
      const white = [238, 241, 245];
      const mix = red.map((channel, i) => Math.round(channel + (white[i] - channel) * settle));
      ctx.strokeStyle = `rgb(${mix[0]} ${mix[1]} ${mix[2]})`;
      ctx.lineWidth = 4;
      const out = (1 - bracket) * 28;
      const left = pad - 18 - out;
      const right = w - pad + 18 + out;
      const top = y - 62 - out;
      const bottom = y + 24 + out;
      const arm = 36;
      ctx.beginPath();
      ctx.moveTo(left, top + arm);
      ctx.lineTo(left, top);
      ctx.lineTo(left + arm, top);
      ctx.moveTo(right - arm, top);
      ctx.lineTo(right, top);
      ctx.lineTo(right, top + arm);
      ctx.moveTo(left, bottom - arm);
      ctx.lineTo(left, bottom);
      ctx.lineTo(left + arm, bottom);
      ctx.moveTo(right - arm, bottom);
      ctx.lineTo(right, bottom);
      ctx.lineTo(right, bottom - arm);
      ctx.stroke();
      if (glow > 0.02) {
        ctx.shadowColor = `rgb(255 69 58 / ${0.45 * glow})`;
        ctx.shadowBlur = 16;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }
    }
  });

  const readoutY = 230 + Math.max(screen.lines.length, trickIndex + 1) * 108 + 16;
  const read = [255, 69, 58].map((channel, i) => Math.round(channel + ([154, 163, 174][i] - channel) * settle));
  ctx.fillStyle = `rgb(${read[0]} ${read[1]} ${read[2]})`;
  ctx.font = "400 40px 'IBM Plex Mono', monospace";
  ctx.textAlign = "left";
  const label = `${formatLatencyCount(screen.latency, count, screen.example)} · Blocked · upsell`;
  ctx.fillText(label, pad, readoutY);
}

function ringGeometry(): BufferGeometry {
  const positions: number[] = [];
  const rx = 2.6;
  const rz = 1.85;
  for (let i = 0; i <= 72; i += 1) {
    const a = (i / 72) * Math.PI * 2;
    positions.push(Math.cos(a) * rx, 0, Math.sin(a) * rz);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  return geometry;
}

function shadowTexture(): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const paint = ctx.createRadialGradient(256, 128, 10, 256, 128, 230);
    paint.addColorStop(0, "rgba(0,0,0,0.9)");
    paint.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = paint;
    ctx.fillRect(0, 0, 512, 256);
  }
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function KioskMesh({
  screen,
  scanRef,
  rootRef,
}: {
  screen: KioskScreen;
  scanRef: RefObject<HTMLDivElement | null>;
  rootRef: RefObject<HTMLDivElement | null>;
}) {
  const group = useRef<Group>(null);
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
  const visible = useRef(true);
  const heroReady = useRef(false);
  const mountedAt = useRef(performance.now());
  const catchStart = useRef<number | null>(null);
  const yaw = useRef(MathUtils.degToRad(-28));
  const drawn = useRef("");

  const materials = useMemo(() => {
    const lit = (color: string) => {
      const material = new MeshStandardMaterial({ color, roughness: 0.8, metalness: 0 });
      material.polygonOffset = true;
      material.polygonOffsetFactor = 1;
      material.polygonOffsetUnits = 1;
      return material;
    };
    const side = lit("#11141A");
    const front = lit("#171B22");
    const top = lit("#1E232B");
    const edge = new LineBasicMaterial({ color: "#323A45" });
    const screenMat = new MeshBasicMaterial({ toneMapped: false });
    const shadowMap = shadowTexture();
    const shadowMat = new MeshBasicMaterial({
      map: shadowMap,
      transparent: true,
      opacity: 0.7,
      depthWrite: false,
      toneMapped: false,
    });
    const ringMat = new LineBasicMaterial({ color: "#232932" });
    const rimMat = new LineBasicMaterial({ color: "#EEF1F5", transparent: true, opacity: 0.55 });
    return { side, front, top, edge, screenMat, shadowMat, shadowMap, ringMat, rimMat };
  }, []);

  const parts = useMemo(() => {
    const base = new BoxGeometry(3, 0.45, 1.9);
    const column = new BoxGeometry(1.1, 4.2, 0.5);
    const reader = new BoxGeometry(1.4, 0.3, 0.35);
    const head = new BoxGeometry(3.9, 3.3, 0.5);
    const screenGeo = new PlaneGeometry(3.45, 2.8);
    const shadow = new PlaneGeometry(6.5, 2.2);
    const rim = new BufferGeometry();
    rim.setAttribute(
      "position",
      new Float32BufferAttribute([-1.95, 1.66, 0.28, 1.7, 1.66, 0.28, -1.95, 1.66, 0.28, -1.95, 0.15, 0.28], 3),
    );
    return {
      base,
      column,
      reader,
      head,
      screenGeo,
      shadow,
      rim,
      baseEdges: new EdgesGeometry(base, 15),
      columnEdges: new EdgesGeometry(column, 15),
      readerEdges: new EdgesGeometry(reader, 15),
      headEdges: new EdgesGeometry(head, 15),
      ring: ringGeometry(),
    };
  }, []);

  const paint = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 1024;
    canvas.height = 830;
    const texture = new CanvasTexture(canvas);
    texture.colorSpace = SRGBColorSpace;
    texture.minFilter = LinearFilter;
    texture.magFilter = LinearFilter;
    materials.screenMat.map = texture;
    return { canvas, texture };
  }, [materials.screenMat]);

  useEffect(() => {
    const node = rootRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        visible.current = !!entry?.isIntersecting;
        if ((entry?.intersectionRatio ?? 0) >= 0.6) heroReady.current = true;
        if (visible.current) invalidate();
      },
      { threshold: [0, 0.6] },
    );
    if (node) observer.observe(node);
    const arm = window.setTimeout(() => invalidate(), 2300);
    const fonts = document.fonts?.ready.then(() => invalidate());
    return () => {
      observer.disconnect();
      window.clearTimeout(arm);
      void fonts;
    };
  }, [invalidate, materials, paint.texture, parts, rootRef]);

  useEffect(() => {
    const onScroll = () => {
      if (visible.current) invalidate();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    invalidate();
    return () => window.removeEventListener("scroll", onScroll);
  }, [invalidate]);

  useFrame((_, delta) => {
    camera.lookAt(0.15, 3.7, 0);
    const root = group.current;
    if (!root || !visible.current) return;
    const hero = rootRef.current;
    let progress = 0;
    if (hero) {
      const rect = hero.getBoundingClientRect();
      const total = rect.height || 1;
      progress = Math.min(1, Math.max(0, -rect.top / total));
    }
    const target = MathUtils.degToRad(-28 + progress * 20);
    yaw.current = MathUtils.damp(yaw.current, target, 4, delta);
    root.rotation.y = yaw.current;

    const now = performance.now();
    if (catchStart.current == null && heroReady.current && now - mountedAt.current >= 2300) {
      catchStart.current = now;
    }
    const elapsed = catchStart.current == null ? -1 : now - catchStart.current;
    const scan = elapsed < 0 ? 0 : Math.min(1, elapsed / 900);
    const catchAt = 900 * 0.46;
    const bracket = elapsed < catchAt ? 0 : easeOut(Math.min(1, (elapsed - catchAt) / 600));
    const glowIn = elapsed < catchAt ? 0 : easeOut(Math.min(1, (elapsed - catchAt) / 300));
    const glowOut = elapsed < catchAt + 1200 ? 0 : easeOut(Math.min(1, (elapsed - catchAt - 1200) / 600));
    const glow = glowIn * (1 - glowOut);
    const settle = elapsed < catchAt + 1200 ? 0 : easeOut(Math.min(1, (elapsed - catchAt - 1200) / 900));
    const count = elapsed < catchAt ? 0 : easeOut(Math.min(1, (elapsed - catchAt) / 400));
    const settled = elapsed > catchAt + 2100;

    const scanEl = scanRef.current;
    if (scanEl) {
      const show = elapsed >= 0 && elapsed <= 980;
      scanEl.style.opacity = show ? "1" : "0";
      scanEl.style.top = `${18 + scan * 52}%`;
    }
    if (hero) hero.dataset.catch = settled ? "settled" : elapsed >= 0 ? "playing" : "wait";

    const signature = `${scan.toFixed(2)}|${bracket.toFixed(2)}|${settle.toFixed(2)}|${count.toFixed(2)}|${glow.toFixed(2)}`;
    if (signature !== drawn.current) {
      drawn.current = signature;
      drawScreen(paint.canvas, screen, bracket, settle, glow, count);
      paint.texture.needsUpdate = true;
    }

    const spinning = Math.abs(yaw.current - target) > 0.002;
    const playing = elapsed >= 0 && !settled;
    if (spinning || playing) invalidate();
  });

  const faces = (front: Material, top: Material): Material[] => [
    materials.side,
    materials.side,
    top,
    materials.side,
    front,
    materials.side,
  ];

  return (
    <group ref={group}>
      <mesh geometry={parts.shadow} material={materials.shadowMat} position={[0.2, 0.001, 0]} rotation={[-Math.PI / 2, 0, 0]} />
      <lineLoop geometry={parts.ring} material={materials.ringMat} position={[0, 0.004, 0]} />
      <mesh geometry={parts.base} material={faces(materials.front, materials.top)} position={[0, 0.225, 0]} />
      <lineSegments geometry={parts.baseEdges} material={materials.edge} position={[0, 0.225, 0]} />
      <mesh geometry={parts.column} material={faces(materials.front, materials.side)} position={[0.1, 2.55, 0]} />
      <lineSegments geometry={parts.columnEdges} material={materials.edge} position={[0.1, 2.55, 0]} />
      <mesh geometry={parts.reader} material={faces(materials.front, materials.side)} position={[0, 3.9, 0.35]} />
      <lineSegments geometry={parts.readerEdges} material={materials.edge} position={[0, 3.9, 0.35]} />
      <group position={[0.2, 6.2, 0.05]} rotation={[-0.21, 0, 0]}>
        <mesh geometry={parts.head} material={faces(materials.front, materials.side)} />
        <lineSegments geometry={parts.headEdges} material={materials.edge} />
        <mesh geometry={parts.screenGeo} material={materials.screenMat} position={[0, 0, 0.27]} />
        <lineSegments geometry={parts.rim} material={materials.rimMat} />
      </group>
    </group>
  );
}

export default function KioskCanvas({
  screen,
  scanRef,
  rootRef,
  onLost,
}: {
  screen: KioskScreen;
  scanRef: RefObject<HTMLDivElement | null>;
  rootRef: RefObject<HTMLDivElement | null>;
  onLost?: () => void;
}) {
  const ready = useRef(false);
  return (
    <Canvas
      dpr={[1, 1.75]}
      frameloop="demand"
      gl={{
        alpha: true,
        antialias: true,
        toneMapping: NoToneMapping,
        powerPreference: "high-performance",
        preserveDrawingBuffer: true,
      }}
      camera={{ fov: 24, position: [7.2, 5.6, 24], near: 0.1, far: 90 }}
      style={{ width: "100%", height: "100%", opacity: 0, transition: `opacity 600ms ${EASE_CSS}` }}
      onCreated={({ camera, gl, invalidate }) => {
        camera.lookAt(0, 3.6, 0);
        gl.toneMapping = NoToneMapping;
        gl.setClearColor(0x000000, 0);
        const lost = (event: Event) => {
          event.preventDefault();
          onLost?.();
        };
        gl.domElement.addEventListener("webglcontextlost", lost);
        if (!ready.current) {
          ready.current = true;
          const shell = gl.domElement.parentElement;
          if (shell) shell.style.opacity = "1";
          gl.domElement.style.opacity = "1";
        }
        invalidate();
      }}
    >
      <ambientLight intensity={2.4} />
      <directionalLight color="#EEF1F5" intensity={2.2} position={[-6, 9, 2]} />
      <KioskMesh screen={screen} scanRef={scanRef} rootRef={rootRef} />
    </Canvas>
  );
}
