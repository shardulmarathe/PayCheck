import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { RefObject } from "react";
import {
  BoxGeometry,
  CanvasTexture,
  EdgesGeometry,
  LineBasicMaterial,
  MathUtils,
  MeshBasicMaterial,
  MeshStandardMaterial,
  NoToneMapping,
  PlaneGeometry,
  SRGBColorSpace,
  Vector3,
  type Group,
  type PointLight,
  type PerspectiveCamera,
  type LineSegments,
  type Mesh,
  type Material,
} from "three";
import { kioskPose } from "./kioskPose";

const SCREEN_W = 4.16;
const SCREEN_H = 2.34; // 16:9, the replay's aspect
const HEAD_Y = 6.2;
const HEAD_Z = 0.05;
const SCREEN_Z = 0.21; // local, in front of the bezel face
const FOV = 24;
const START_YAW = MathUtils.degToRad(-18);
const START_TILT = -0.21;

const BEZEL_W = 4.7;
const BEZEL_H = 2.95;
const BEZEL_Z = 0.2;


/** Normalised pointer, eased each frame (camera parallax). */
const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
if (typeof window !== "undefined") {
  window.addEventListener(
    "pointermove",
    (e) => {
      pointer.tx = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.ty = (e.clientY / window.innerHeight) * 2 - 1;
    },
    { passive: true },
  );
}

const target = new Vector3();
const look = new Vector3();
const corner = new Vector3();

function projectRect(
  head: Group,
  w: number,
  hgt: number,
  zLocal: number,
  camera: Parameters<typeof target.project>[0],
  width: number,
  height: number,
) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [sx, sy] of [
    [-1, -1],
    [1, -1],
    [1, 1],
    [-1, 1],
  ]) {
    corner.set((sx * w) / 2, (sy * hgt) / 2, zLocal).applyMatrix4(head.matrixWorld);
    target.copy(corner).project(camera);
    const px = ((target.x + 1) / 2) * width;
    const py = ((1 - target.y) / 2) * height;
    minX = Math.min(minX, px);
    maxX = Math.max(maxX, px);
    minY = Math.min(minY, py);
    maxY = Math.max(maxY, py);
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

function Kiosk({
  poster,
  overlayRef,
  deviceRef,
  onArrive,
  onReady,
}: {
  poster: string;
  overlayRef: RefObject<HTMLDivElement | null>;
  deviceRef: RefObject<HTMLDivElement | null>;
  onArrive: () => void;
  onReady: () => void;
}) {
  const bezelMesh = useRef<Mesh>(null);
  const bezelLines = useRef<LineSegments>(null);
  const root = useRef<Group>(null);
  const head = useRef<Group>(null);
  const invalidate = useThree((state) => state.invalidate);
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const arrived = useRef(false);
  const drawn = useRef(false);
  const rimRed = useRef<PointLight>(null);
  const gl = useThree((state) => state.gl);

  const materials = useMemo(() => {
    const lit = (color: string) => {
      const material = new MeshStandardMaterial({ color, roughness: 0.42, metalness: 0.35 });
      material.polygonOffset = true;
      material.polygonOffsetFactor = 1;
      material.polygonOffsetUnits = 1;
      return material;
    };
    const screenMat = new MeshBasicMaterial({ color: "#0A0C0F", toneMapped: false });
    // The site's three build (vendor/three-lite.js) has no TextureLoader; an <img> wrapped in a CanvasTexture does the same.
    const image = new Image();
    image.onload = () => {
      const texture = new CanvasTexture(image);
      texture.colorSpace = SRGBColorSpace;
      texture.needsUpdate = true;
      screenMat.map = texture;
      screenMat.color.set("#ffffff");
      screenMat.needsUpdate = true;
      invalidate();
    };
    image.src = poster;
    return {
      side: lit("#1B2029"),
      front: lit("#151920"),
      top: lit("#2A313C"),
      edge: new LineBasicMaterial({ color: "#4A5562" }),
      ring: new LineBasicMaterial({ color: "#232932" }),
      screenMat,
    };
  }, [poster, invalidate]);

  const parts = useMemo(() => {
    const base = new BoxGeometry(3, 0.45, 1.9);
    const column = new BoxGeometry(1.0, 4.3, 0.5);
    const reader = new BoxGeometry(1.4, 0.3, 0.35);
    const bezel = new BoxGeometry(BEZEL_W, BEZEL_H, 0.4);
    return {
      base,
      column,
      reader,
      bezel,
      screen: new PlaneGeometry(SCREEN_W, SCREEN_H),
      baseEdges: new EdgesGeometry(base, 15),
      columnEdges: new EdgesGeometry(column, 15),
      readerEdges: new EdgesGeometry(reader, 15),
      bezelEdges: new EdgesGeometry(bezel, 15),
    };
  }, []);

  // Idle motion (light sweep, pointer parallax) needs frames; run them only while the hero is on screen.
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let visible = true;
    let frame = 0;
    const io = new IntersectionObserver(([entry]) => {
      visible = !!entry?.isIntersecting;
    });
    io.observe(gl.domElement);
    const loop = () => {
      if (visible) invalidate();
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frame);
      io.disconnect();
    };
  }, [gl, invalidate]);

  useEffect(() => {
    kioskPose.invalidate = () => invalidate();
    invalidate();
    return () => {
      kioskPose.invalidate = () => {};
    };
  }, [invalidate]);

  useFrame((state) => {
    const z = Math.min(1, Math.max(0, kioskPose.zoom));
    const time = state.clock.elapsedTime;
    pointer.x += (pointer.tx - pointer.x) * 0.06;
    pointer.y += (pointer.ty - pointer.y) * 0.06;
    const aspect = size.width / Math.max(1, size.height);
    const narrow = size.width < 600;
    const tan = Math.tan(MathUtils.degToRad(FOV / 2));
    // End: frontal; the camera sits a little low so the kiosk's neck stays visible below the screen.
    const fillW = narrow ? 0.84 : 0.62;
    const fillH = narrow ? 0.74 : 0.7;
    const endDist = Math.max(SCREEN_W / (fillW * 2 * tan * aspect), SCREEN_H / (fillH * 2 * tan));
    const lift = (narrow ? 0.12 : 0.08) * endDist * tan; // half of ndc offset × visible height
    // Start: pulled back on the whole kiosk (about 8.6 units tall), seen from a quarter angle.
    const startDist = Math.max(8.6 / (0.88 * 2 * tan), 5 / (0.8 * 2 * tan * aspect));
    const screenCenterY = HEAD_Y;
    const screenCenterZ = HEAD_Z + SCREEN_Z;

    // Pointer parallax: the camera slides (it never turns), so the screen stays a flat rectangle for the HTML overlay
    // while the neck, base and lights at other depths shift against it. Before arrival it also drifts a little.
    const px = pointer.x * MathUtils.lerp(0.9, 0.28, z) + (1 - z) * Math.sin(time * 0.6) * 0.25;
    const py = -pointer.y * MathUtils.lerp(0.5, 0.16, z);
    camera.position.set(
      MathUtils.lerp(startDist * 0.3, 0, z) + px,
      MathUtils.lerp(5.4, screenCenterY - lift, z) + py,
      MathUtils.lerp(startDist * 0.95, screenCenterZ + endDist, z),
    );
    look.set(px * z, MathUtils.lerp(4.1, screenCenterY - lift, z) + py * z, MathUtils.lerp(0, screenCenterZ, z));
    // End pose seen slightly from the upper left: the camera slides (direction unchanged, so the screen stays a
    // rectangle for the HTML overlay) and a lens shift re-centres the screen. The bezel's side and top faces and the
    // neck below then show real depth.
    const ox = (narrow ? -1.9 : -3.2) * z;
    const oy = (narrow ? 0.9 : 1.5) * z;
    camera.position.x += ox;
    camera.position.y += oy;
    look.x += ox;
    look.y += oy;
    camera.lookAt(look);
    const persp = camera as PerspectiveCamera;
    const depth = Math.max(0.5, camera.position.z - screenCenterZ);
    const shiftX = ((-ox / (depth * tan * aspect)) * size.width) / 2;
    const shiftY = ((oy / (depth * tan)) * size.height) / 2;
    if (Math.abs(shiftX) + Math.abs(shiftY) > 0.01) persp.setViewOffset(size.width, size.height, shiftX, shiftY, size.width, size.height);
    else if (persp.view?.enabled) persp.clearViewOffset();
    if (rimRed.current) rimRed.current.position.x = -4 + Math.sin(time * 0.5) * 1.5;
    camera.updateMatrixWorld();

    const r = root.current;
    const h = head.current;
    if (!r || !h) return;
    r.rotation.y = MathUtils.lerp(START_YAW, 0, z);
    h.rotation.x = MathUtils.lerp(START_TILT, 0, z);
    r.updateMatrixWorld(true);
    if (!drawn.current) {
      drawn.current = true;
      // This frame renders right after the callbacks; tell the page on the next paint.
      requestAnimationFrame(() => onReady());
    }

    // Lay the HTML screen over the projected screen rectangle; show it only once the camera is frontal.
    // The device frame (HTML) covers the projected bezel; the 3D bezel hides once the frame has faded in.
    const device = deviceRef.current;
    if (device) {
      const rect = projectRect(h, BEZEL_W, BEZEL_H, BEZEL_Z, camera, size.width, size.height);
      device.style.left = `${rect.x}px`;
      device.style.top = `${rect.y}px`;
      device.style.width = `${rect.w}px`;
      device.style.height = `${rect.h}px`;
      device.dataset.on = z >= 0.999 ? "1" : "0";
    }
    if (bezelMesh.current) bezelMesh.current.visible = !kioskPose.bezelHidden;
    if (bezelLines.current) bezelLines.current.visible = !kioskPose.bezelHidden;

    const overlay = overlayRef.current;
    if (overlay) {
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const [sx, sy] of [
        [-1, -1],
        [1, -1],
        [1, 1],
        [-1, 1],
      ]) {
        corner.set((sx * SCREEN_W) / 2, (sy * SCREEN_H) / 2, SCREEN_Z).applyMatrix4(h.matrixWorld);
        target.copy(corner).project(camera);
        const px = ((target.x + 1) / 2) * size.width;
        const py = ((1 - target.y) / 2) * size.height;
        minX = Math.min(minX, px);
        maxX = Math.max(maxX, px);
        minY = Math.min(minY, py);
        maxY = Math.max(maxY, py);
      }
      overlay.style.left = `${minX}px`;
      overlay.style.top = `${minY}px`;
      overlay.style.width = `${maxX - minX}px`;
      overlay.style.height = `${maxY - minY}px`;
      const done = z >= 0.999;
      overlay.dataset.on = done ? "1" : "0";
      if (done && !arrived.current) {
        arrived.current = true;
        onArrive();
      }
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
    <group ref={root}>
      <pointLight ref={rimRed} color="#ff453a" intensity={9} distance={14} position={[-4, 7.5, -2.5]} />
      <pointLight color="#dfe6f0" intensity={20} distance={14} position={[4.2, 7.4, -1.6]} />
      <pointLight color="#cfe0ff" intensity={14} distance={16} position={[2.5, 8, 5]} />
      <mesh geometry={parts.base} material={faces(materials.front, materials.top)} position={[0, 0.225, 0]} />
      <lineSegments geometry={parts.baseEdges} material={materials.edge} position={[0, 0.225, 0]} />
      <mesh geometry={parts.column} material={faces(materials.front, materials.side)} position={[0, 2.6, 0]} />
      <lineSegments geometry={parts.columnEdges} material={materials.edge} position={[0, 2.6, 0]} />
      <mesh geometry={parts.reader} material={faces(materials.front, materials.side)} position={[0, 3.9, 0.35]} />
      <lineSegments geometry={parts.readerEdges} material={materials.edge} position={[0, 3.9, 0.35]} />
      <group ref={head} position={[0, HEAD_Y, HEAD_Z]}>
        <mesh ref={bezelMesh} geometry={parts.bezel} material={faces(materials.front, materials.top)} />
        <lineSegments ref={bezelLines} geometry={parts.bezelEdges} material={materials.edge} />
        <mesh geometry={parts.screen} material={materials.screenMat} position={[0, 0, SCREEN_Z]} />
      </group>
    </group>
  );
}

export default function KioskZoomCanvas({
  poster,
  overlayRef,
  deviceRef,
  onArrive,
  onLost,
  onReady,
}: {
  poster: string;
  overlayRef: RefObject<HTMLDivElement | null>;
  deviceRef: RefObject<HTMLDivElement | null>;
  onArrive: () => void;
  onLost: () => void;
  onReady: () => void;
}) {
  return (
    <Canvas
      className="kz-canvas"
      dpr={[1, 2]}
      frameloop="demand"
      gl={{ alpha: true, antialias: true, toneMapping: NoToneMapping, powerPreference: "high-performance" }}
      camera={{ fov: FOV, near: 0.1, far: 120, position: [8, 5.4, 30] }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 0);
        gl.domElement.addEventListener("webglcontextlost", (event) => {
          event.preventDefault();
          onLost();
        });
      }}
    >
      <ambientLight intensity={2.2} />
      <directionalLight color="#EEF1F5" intensity={2.4} position={[-6, 9, 6]} />
      <Kiosk poster={poster} overlayRef={overlayRef} deviceRef={deviceRef} onArrive={onArrive} onReady={onReady} />
    </Canvas>
  );
}
