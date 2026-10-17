import { ContactShadows, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { MathUtils, type Group } from "three";

/** Scroll progress across the first viewport, mapped to a small yaw. */
function scrollYaw(): number {
  const view = window.innerHeight || 1;
  const progress = Math.min(1, Math.max(0, window.scrollY / view));
  return -0.45 + progress * 0.9;
}

function Kiosk() {
  const ref = useRef<Group>(null);
  const ready = useRef(false);
  const invalidate = useThree((state) => state.invalidate);

  useEffect(() => {
    const onScroll = () => invalidate();
    window.addEventListener("scroll", onScroll, { passive: true });
    invalidate();
    return () => window.removeEventListener("scroll", onScroll);
  }, [invalidate]);

  useFrame((_, delta) => {
    const group = ref.current;
    if (!group) return;
    const target = scrollYaw();
    if (!ready.current) {
      group.rotation.y = target;
      ready.current = true;
      return;
    }
    const next = MathUtils.damp(group.rotation.y, target, 2.2, delta);
    group.rotation.y = next;
    if (Math.abs(next - target) > 0.002) invalidate();
  });

  return (
    <group ref={ref} position={[0, -0.05, 0]}>
      <RoundedBox args={[1.2, 0.08, 0.72]} radius={0.02} position={[0, -0.9, 0]} smoothness={4}>
        <meshStandardMaterial color="#11141A" />
      </RoundedBox>
      <RoundedBox args={[0.92, 1.4, 0.46]} radius={0.03} position={[0, -0.14, 0]} smoothness={4}>
        <meshStandardMaterial color="#171B22" />
      </RoundedBox>
      <mesh position={[0, 0.08, 0.24]}>
        <planeGeometry args={[0.7, 0.9]} />
        <meshStandardMaterial color="#0A0C0F" />
      </mesh>
      <mesh position={[0, 0.28, 0.245]}>
        <planeGeometry args={[0.46, 0.035]} />
        <meshStandardMaterial color="#EEF1F5" />
      </mesh>
      <mesh position={[0, 0.18, 0.245]}>
        <planeGeometry args={[0.46, 0.035]} />
        <meshStandardMaterial color="#9AA3AE" />
      </mesh>
      <mesh position={[0, 0.08, 0.245]}>
        <planeGeometry args={[0.28, 0.035]} />
        <meshStandardMaterial color="#323A45" />
      </mesh>
      <mesh position={[0, -0.55, 0.24]}>
        <boxGeometry args={[0.32, 0.045, 0.02]} />
        <meshStandardMaterial color="#232932" />
      </mesh>
    </group>
  );
}

/** Placeholder checkout kiosk. The v3 frame replaces this mesh. */
export default function KioskCanvas() {
  return (
    <Canvas
      camera={{ position: [0.2, 0.72, 3.6], fov: 32 }}
      dpr={[1, 1.5]}
      frameloop="demand"
      gl={{ antialias: true, alpha: true }}
      style={{ width: "100%", height: "100%" }}
      onCreated={({ invalidate }) => invalidate()}
    >
      <ambientLight intensity={0.72} />
      <directionalLight position={[2.4, 3.4, 4.2]} intensity={1.55} />
      <Kiosk />
      <ContactShadows position={[0, -0.96, 0]} opacity={0.4} scale={6} blur={2.4} far={2.2} color="#000000" frames={1} />
    </Canvas>
  );
}
