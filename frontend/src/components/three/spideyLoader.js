import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

export const SPIDEY_CLIPS = [
    'Idle_Breath',
    'Tetrapod_Walk',
    'Happy_Bounce',
    'Front_Wave',
    'Reference_Pose',
];

/**
 * Loads the animated S.P.I.D.E.Y. GLB companion model, normalizes its scale/bounds,
 * and wires a Three.js AnimationMixer with smooth cross-fade clip playback.
 */
export async function loadSpideyAICompanion(
    scene,
    glbUrl = '/spidey-ai-companion-animated.glb'
) {
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(glbUrl);
    const spidey = gltf.scene;

    // Normalize scale and center at origin so it frames reliably in any viewport
    const box = new THREE.Box3().setFromObject(spidey);
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);

    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    const scale = 1.95 / maxDim;
    spidey.scale.setScalar(scale);
    spidey.position.set(-center.x * scale, -center.y * scale - 0.08, -center.z * scale);

    scene.add(spidey);

    const mixer = new THREE.AnimationMixer(spidey);
    const actions = new Map();

    for (const clip of gltf.animations) {
        actions.set(clip.name, mixer.clipAction(clip));
    }

    let currentAction = actions.get('Idle_Breath') || gltf.animations[0] ? actions.get(gltf.animations[0].name) : null;
    currentAction?.play();

    return {
        spidey,
        mixer,
        actions,
        playClip(name, fadeSeconds = 0.35) {
            const next = actions.get(name);
            if (!next || next === currentAction) return;
            currentAction?.fadeOut(fadeSeconds);
            next.reset().fadeIn(fadeSeconds).play();
            currentAction = next;
        },
        dispose() {
            mixer.stopAllAction();
            spidey.traverse((obj) => {
                if (obj.geometry) obj.geometry.dispose();
                if (obj.material) {
                    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
                    for (const mat of mats) {
                        if (mat.map) mat.map.dispose();
                        if (mat.normalMap) mat.normalMap.dispose();
                        if (mat.roughnessMap) mat.roughnessMap.dispose();
                        if (mat.metalnessMap) mat.metalnessMap.dispose();
                        if (mat.emissiveMap) mat.emissiveMap.dispose();
                        mat.dispose();
                    }
                }
            });
            scene.remove(spidey);
        },
    };
}
