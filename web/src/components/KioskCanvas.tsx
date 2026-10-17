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
import { kioskPose, type KioskMode } from "./kioskPose";

export interface KioskScreen {
  url: string;
  lines: { label: string; value: string; trick?: boolean }[];
  latency: number | null;
  example: boolean;
  quote: string;
  catchRate: number | null;
  readout: string;
  /** Blank screen. Used when the replay recording is withheld. */
  quiet?: boolean;
}

const EASE_CSS = "cubic-bezier(0.2, 0.8, 0.2, 1)";

function drawQuiet(ctx: CanvasRenderingContext2D, w: number, h: number, mode: KioskMode, catchRate: number | null) {
  ctx.fillStyle = "#171B22";
  ctx.fillRect(0, 0, w, h);
  if (mode === "benchmarks") {
    const track = w * 0.62;
    const x = (w - track) / 2;
    const y = h * 0.48;
    ctx.fillStyle = "#232932";
    ctx.fillRect(x, y, track, 10);
    const pct = catchRate == null ? 0 : Math.min(1, Math.max(0, catchRate / 100));
    ctx.fillStyle = "#EEF1F5";
    ctx.fillRect(x, y, track * pct, 10);
    return;
  }
  if (mode === "design") {
    ctx.strokeStyle = "#232932";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.ellipse(w / 2, h / 2, w * 0.22, h * 0.16, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "#EEF1F5";
    ctx.beginPath();
    ctx.arc(w / 2 + w * 0.22, h / 2, 12, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  for (let row = 0; row < 3; row += 1) {
    ctx.fillStyle = "#232932";
    ctx.fillRect(w * 0.22, h * 0.32 + row * 78, w * 0.56, 10);
  }
}

function drawNeutral(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.fillStyle = "#11141A";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#323A45";
  ctx.lineWidth = 2;
  ctx.strokeRect(12, 12, w - 24, h - 24);
  ctx.fillStyle = "#171B22";
  ctx.fillRect(48, 72, w - 96, 56);
}

function drawCheckout(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  screen: KioskScreen,
  bracket: number,
  settle: number,
  glow: number,
  readout: number,
) {
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
        ctx.shadowColor = "rgb(255 69 58 / 0.20)";
        ctx.shadowBlur = 12 * glow;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }
    }
  });

  if (readout > 0.02) {
    const readoutY = 230 + Math.max(screen.lines.length, trickIndex + 1) * 108 + 16;
    ctx.save();
    ctx.globalAlpha = readout;
    ctx.fillStyle = "#9AA3AE";
    ctx.font = "400 40px 'IBM Plex Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillText(screen.readout, pad, readoutY);
    if (screen.quote) {
      ctx.font = "400 32px 'IBM Plex Mono', monospace";
      ctx.fillText(`"${screen.quote}"`, pad, readoutY + 64, w - pad * 2);
    }
    ctx.restore();
  }
  void h;
}

function drawScreen(canvas: HTMLCanvasElement, screen: KioskScreen) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  const paint = (mode: KioskMode) => {
    if (mode === "demo") {
      if (screen.quiet) drawNeutral(ctx, w, h);
      else drawCheckout(ctx, w, h, screen, kioskPose.bracket, kioskPose.settle, kioskPose.glow, kioskPose.readout);
      return;
    }
    drawQuiet(ctx, w, h, mode, screen.catchRate);
  };
  ctx.clearRect(0, 0, w, h);
  if (kioskPose.mode === kioskPose.modeFrom || kioskPose.modeMix >= 0.999) {
    paint(kioskPose.mode);
    return;
  }
  ctx.save();
  ctx.globalAlpha = 1 - kioskPose.modeMix;
  paint(kioskPose.modeFrom);
  ctx.restore();
  ctx.save();
  ctx.globalAlpha = kioskPose.modeMix;
  paint(kioskPose.mode);
  ctx.restore();
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
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.beginPath();
    ctx.ellipse(256, 128, 180, 70, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

function LightRig() {
  const amb = useRef<{ intensity: number } | null>(null);
  const dir = useRef<{ intensity: number } | null>(null);
  useFrame(() => {
    const presence = kioskPose.presence;
    if (amb.current) amb.current.intensity = 2.4 * presence;
    if (dir.current) dir.current.intensity = 2.2 * presence;
  });
  return (
    <>
      <ambientLight ref={amb} intensity={2.4} />
      <directionalLight ref={dir} color="#EEF1F5" intensity={2.2} position={[-6, 9, 2]} />
    </>
  );
}

function KioskMesh({
  screen,
  scanRef,
}: {
  screen: KioskScreen;
  scanRef: RefObject<HTMLDivElement | null>;
}) {
  const group = useRef<Group>(null);
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
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
    kioskPose.invalidate = () => invalidate();
    const fonts = document.fonts?.ready.then(() => invalidate());
    invalidate();
    return () => {
      kioskPose.invalidate = () => {};
      void fonts;
    };
  }, [invalidate]);

  useFrame(() => {
    const pull = kioskPose.cameraPull;
    camera.position.set(5.2 + pull * 2, 4.4 + pull * 1.2, 14 + pull * 10);
    camera.lookAt(0.15, 3.7, 0);
    const root = group.current;
    if (!root) return;
    root.rotation.y = MathUtils.degToRad(-18) + kioskPose.yaw;
    materials.edge.color.set(kioskPose.presence > 0.7 ? "#323A45" : "#232932");
    materials.rimMat.opacity = kioskPose.presence > 0.7 ? 0.55 : 0;

    const scanEl = scanRef.current;
    if (scanEl) {
      const show = kioskPose.sweep > 0.02 && kioskPose.sweep < 0.98 && kioskPose.cameraPull < 0.2;
      scanEl.style.opacity = show ? "1" : "0";
      scanEl.style.top = `${18 + kioskPose.sweep * 52}%`;
    }

    const signature = [
      kioskPose.mode,
      kioskPose.modeFrom,
      kioskPose.modeMix.toFixed(2),
      kioskPose.bracket.toFixed(2),
      kioskPose.settle.toFixed(2),
      kioskPose.glow.toFixed(2),
      kioskPose.readout.toFixed(2),
      screen.readout,
    ].join("|");
    if (signature !== drawn.current) {
      drawn.current = signature;
      drawScreen(paint.canvas, screen);
      paint.texture.needsUpdate = true;
    }
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
  onLost,
}: {
  screen: KioskScreen;
  scanRef: RefObject<HTMLDivElement | null>;
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
      <LightRig />
      <KioskMesh screen={screen} scanRef={scanRef} />
    </Canvas>
  );
}
