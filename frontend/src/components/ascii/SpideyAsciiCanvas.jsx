import { useEffect, useRef } from 'react';
import { useSpideyBrain } from '../../context/SpideyBrainContext';
import { getSharedAudioQueue } from '../../services/voiceService';

// Warm S.P.I.D.E.Y Obsidian / Warm Ash / Burnt Ember / Incandescent Highlight palette
// 0..7   : Deep obsidian-ash -> warm bone cream (valleys & slopes)
// 8..15  : Deep ember -> burnt orange (#D95D24) -> hot glow (#FFD4A8) (crests & active interaction)
// 16..18 : Subtle background coordinate markers '+' / '·'
const PALETTE = [
    // Deep Ash -> Bone Cream (0..7)
    '#171513', '#23201d', '#332f2a', '#48423c', '#635b53', '#857c72', '#b0a79d', '#e5dfd6',
    // Burnt Ember -> Incandescent Highlight (8..15)
    '#4d1f0b', '#752d0f', '#9e3e15', '#c44f1c', '#d95d24', '#f27029', '#ff944d', '#ffd4a8',
    // Subtle background coordinate markers (16..18)
    '#141210', '#1f1c19', '#4a210f',
];

const MAX_RIPPLES = 10;
const MAX_PLUCKS = 14;
const MAX_SPARKS = 28;
const MAX_SCANS = 3;

// Physical QWERTY spatial layout -> normalized X [-1..1] and row depth Z [-0.4..0.55]
const QWERTY_ROWS = [
    { keys: '1234567890-=', z: -0.45 },
    { keys: 'qwertyuiop[]', z: -0.10 },
    { keys: "asdfghjkl;'", z: 0.22 },
    { keys: 'zxcvbnm,./', z: 0.52 },
];

const KEY_COORDS = new Map();
for (const row of QWERTY_ROWS) {
    const len = row.keys.length;
    for (let i = 0; i < len; i++) {
        const nx = (i / (len - 1)) * 2 - 1; // -1 (left) -> +1 (right)
        KEY_COORDS.set(row.keys[i], { nx, z: row.z });
    }
}

function getKeySpatialPos(rawKey) {
    const k = String(rawKey || '').toLowerCase();
    if (k === ' ') return { nx: 0, z: 0.65, isSpace: true };
    const mapped = KEY_COORDS.get(k);
    if (mapped) return { nx: mapped.nx, z: mapped.z, isSpace: false };
    // Fallback hash for shifted punctuation / other keys
    const code = k.charCodeAt(0) || 64;
    return { nx: ((code * 37) % 100) / 50 - 1, z: 0.15, isSpace: false };
}

/**
 * Full-screen interactive 3D Kinetic Topographic ASCII Wave Field background for S.P.I.D.E.Y.
 * - Mouse: silky magnetic ridge swell under cursor + gentle 3D parallax + click shockwaves.
 * - Keyboard: physically QWERTY-mapped synthesizer string-plucks along matching terrain columns,
 *   delicate rising typed-character ember sparks, Spacebar central breath, Backspace valley pull,
 *   and a sleek bottom-to-top transmission scanline sweep on Enter/Send.
 * - Voice & AI: live acoustic wave elevation and thinking/streaming momentum.
 */
export default function SpideyAsciiCanvas({ className = '' }) {
    const containerRef = useRef(null);
    const canvasRef = useRef(null);
    const brain = useSpideyBrain();
    const brainRef = useRef(brain);

    useEffect(() => {
        brainRef.current = brain;
    }, [brain]);

    useEffect(() => {
        const container = containerRef.current;
        const canvas = canvasRef.current;
        if (!container || !canvas) return undefined;

        const ctx = canvas.getContext('2d', { alpha: false });
        if (!ctx) return undefined;

        const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

        let cols = 150;
        let rows = 56;
        let cellW = 8.4;
        let cellH = 14.4;
        let fontSize = 12.5;
        let dpr = Math.min(window.devicePixelRatio || 1, 2);

        let zBuf = new Float32Array(cols * rows);
        let charBuf = new Uint16Array(cols * rows);
        let colorBuf = new Uint8Array(cols * rows);
        const bucketIndices = Array.from({ length: PALETTE.length }, () => []);

        const resize = () => {
            const rect = container.getBoundingClientRect();
            const width = Math.max(300, Math.floor(rect.width));
            const height = Math.max(240, Math.floor(rect.height));
            dpr = Math.min(window.devicePixelRatio || 1, 2);

            canvas.width = Math.floor(width * dpr);
            canvas.height = Math.floor(height * dpr);
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;

            const isSmall = width < 640;
            fontSize = isSmall ? 11 : 12.5;
            cellW = isSmall ? 7.2 : 8.4;
            cellH = isSmall ? 12.6 : 14.4;

            cols = Math.max(44, Math.floor(width / cellW));
            rows = Math.max(22, Math.floor(height / cellH));

            zBuf = new Float32Array(cols * rows);
            charBuf = new Uint16Array(cols * rows);
            colorBuf = new Uint8Array(cols * rows);
        };

        resize();
        const resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(container);

        // Mouse parallax & wake state
        const pointer = {
            targetX: 0,
            targetY: 0,
            x: 0,
            y: 0,
            speed: 0,
            active: false,
            lastTrailT: 0,
        };

        // Interactive physics channels:
        // 1. ripples: mouse clicks & trailing wake
        // 2. plucks : QWERTY-mapped harmonic ridge-string plucks (and Backspace valley pull)
        // 3. sparks : floating rising ASCII character sparks emitted from each key column
        // 4. scans  : sleek horizontal transmission scanline sweeps on Enter / Send
        const ripples = [];
        const plucks = [];
        const sparks = [];
        const scans = [];

        let simT = 0;
        let flowGlow = 0;

        const spawnRipple = (wx, wz, { amp = 0.28, speed = 2.4, width = 0.42, life = 2.0, ember = 1.0 } = {}) => {
            ripples.push({ wx, wz, birth: simT, amp, speed, width, life, ember });
            if (ripples.length > MAX_RIPPLES) ripples.shift();
        };

        const mapScreenToWorld = (clientX, clientY) => {
            const nx = (clientX / Math.max(1, window.innerWidth) - 0.5) * 2;
            const ny = (clientY / Math.max(1, window.innerHeight) - 0.5) * 2;
            return { nx, ny, wx: nx * 2.15, wz: ny * 1.45 };
        };

        const onWindowPointerMove = (e) => {
            const mapped = mapScreenToWorld(e.clientX, e.clientY);
            const dx = mapped.nx - pointer.targetX;
            const dy = mapped.ny - pointer.targetY;
            const moveDist = Math.hypot(dx, dy);

            pointer.targetX = mapped.nx;
            pointer.targetY = mapped.ny;
            pointer.active = true;
            pointer.speed = Math.min(2.4, pointer.speed + moveDist * 14);

            if (moveDist > 0.018 && simT - pointer.lastTrailT > 0.14) {
                pointer.lastTrailT = simT;
                spawnRipple(mapped.wx, mapped.wz, {
                    amp: Math.min(0.22, 0.09 + moveDist * 2.0),
                    speed: 1.75,
                    width: 0.48,
                    life: 1.55,
                    ember: 0.7,
                });
            }
        };

        const onWindowPointerLeave = () => {
            pointer.active = false;
        };

        const onWindowPointerDown = (e) => {
            const mapped = mapScreenToWorld(e.clientX, e.clientY);
            spawnRipple(mapped.wx, mapped.wz, {
                amp: 0.40,
                speed: 2.65,
                width: 0.38,
                life: 2.2,
                ember: 1.15,
            });
        };

        // Tactile QWERTY Keyboard Interaction:
        // - Letters pluck the exact matching X-column of the 3D terrain like a glowing synth string
        //   AND release a soft rising character spark from the composer line.
        // - Space sends a calm, wide symmetric breath across the middle ridge.
        // - Backspace gently pulls a smooth receding dimple downward.
        const onKeystroke = (e) => {
            const rawKey = e?.detail?.key || '';
            const isDelete = Boolean(e?.detail?.isDelete);
            flowGlow = Math.min(0.85, flowGlow + 0.14);

            if (isDelete) {
                plucks.push({
                    wx: 1.25 + (Math.random() - 0.5) * 0.4,
                    wz: 0.1,
                    birth: simT,
                    amp: -0.22, // smooth downward pull
                    sigmaX: 0.72,
                    freq: 7.5,
                    life: 0.95,
                    ember: 0.35,
                    wide: false,
                });
                if (plucks.length > MAX_PLUCKS) plucks.shift();
                return;
            }

            const pos = getKeySpatialPos(rawKey);
            const wx = pos.nx * 1.95;

            if (pos.isSpace) {
                // Wide, serene central ridge breath
                plucks.push({
                    wx: 0,
                    wz: 0.3,
                    birth: simT,
                    amp: 0.18,
                    sigmaX: 1.85,
                    freq: 5.2,
                    life: 1.15,
                    ember: 0.55,
                    wide: true,
                });
            } else {
                // Targeted harmonic string pluck right at this key's physical column!
                plucks.push({
                    wx,
                    wz: pos.z,
                    birth: simT,
                    amp: 0.24,
                    sigmaX: 0.42,
                    freq: 10.5,
                    life: 1.05,
                    ember: 0.92,
                    wide: false,
                });

                // Delicate rising typed-character ember spark floating up from the composer
                if (rawKey.length === 1 && rawKey.trim()) {
                    const baseCol = Math.round(cols * (0.5 + pos.nx * 0.34));
                    sparks.push({
                        col: Math.max(4, Math.min(cols - 5, baseCol)),
                        row: rows - 4,
                        vx: (Math.random() - 0.5) * 2.2,
                        vy: -(9.5 + Math.random() * 5.0),
                        charCode: rawKey.charCodeAt(0),
                        birth: simT,
                        life: 0.95 + Math.random() * 0.35,
                    });
                    if (sparks.length > MAX_SPARKS) sparks.shift();
                }
            }

            if (plucks.length > MAX_PLUCKS) plucks.shift();
        };

        // Enter / Send: crisp horizontal ember scanline sweeps smoothly from front to back across the terrain!
        const onSubmitWave = () => {
            flowGlow = 1.0;
            scans.push({
                birth: simT,
                life: 1.45,
                startZ: 1.65,
                endZ: -1.75,
                width: 0.34,
                amp: 0.34,
            });
            if (scans.length > MAX_SCANS) scans.shift();
        };

        window.addEventListener('pointermove', onWindowPointerMove, { passive: true });
        document.addEventListener('pointerleave', onWindowPointerLeave, { passive: true });
        window.addEventListener('pointerdown', onWindowPointerDown, { passive: true });
        window.addEventListener('spidey:keystroke', onKeystroke);
        window.addEventListener('spidey:submit_wave', onSubmitWave);

        let isTabVisible = !document.hidden;
        const onVisibility = () => {
            isTabVisible = !document.hidden;
        };
        document.addEventListener('visibilitychange', onVisibility);

        let lastTime = performance.now();
        let lastSeenPulseTime = 0;
        let lastVoiceRippleT = 0;
        let energySmooth = 0;
        let rafId = 0;

        const plot = (wx, wy, wz, chCode, colorIdx, camDist, fovX, fovY, cx, cy) => {
            const cz = camDist - wz;
            if (cz < 0.45) return;
            const invZ = 1 / cz;
            const col = Math.round(cx + wx * fovX * invZ);
            const row = Math.round(cy - wy * fovY * invZ);
            if (col < 0 || col >= cols || row < 0 || row >= rows) return;
            const idx = row * cols + col;
            if (invZ > zBuf[idx]) {
                zBuf[idx] = invZ;
                charBuf[idx] = chCode;
                colorBuf[idx] = colorIdx;
            }
        };

        const animate = (now) => {
            rafId = requestAnimationFrame(animate);
            if (!isTabVisible) {
                lastTime = now;
                return;
            }

            const rawDt = Math.min((now - lastTime) / 1000, 0.05);
            lastTime = now;
            const dt = prefersReducedMotion ? rawDt * 0.2 : rawDt;

            const pLerp = Math.min(1, dt * 7.5);
            pointer.x += (pointer.targetX - pointer.x) * pLerp;
            pointer.y += (pointer.targetY - pointer.y) * pLerp;
            pointer.speed = Math.max(0, pointer.speed - dt * 3.8);
            flowGlow = Math.max(0, flowGlow - dt * 1.15);

            const currentBrain = brainRef.current;
            const brainState = currentBrain?.brainStateRef?.current || 'idle';
            const micLevel = currentBrain?.audioLevelRef?.current || 0;
            const ttsLevel = getSharedAudioQueue()?.getOutputLevel?.() || 0;
            let liveAudio = Math.max(micLevel, ttsLevel);
            if ((brainState === 'speaking' || brainState === 'streaming') && liveAudio < 0.09) {
                liveAudio = 0.20 + 0.14 * Math.sin(simT * 7.8);
            }
            energySmooth += (liveAudio - energySmooth) * Math.min(1, dt * 8.0);

            const ctxPulse = currentBrain?.pulseRef?.current;
            if (ctxPulse && ctxPulse.time > lastSeenPulseTime) {
                lastSeenPulseTime = ctxPulse.time;
                scans.push({
                    birth: simT,
                    life: 1.35,
                    startZ: 1.5,
                    endZ: -1.65,
                    width: 0.32,
                    amp: 0.26,
                });
                if (scans.length > MAX_SCANS) scans.shift();
            }

            const isListening = brainState === 'listening';
            const isThinking = brainState === 'thinking' || brainState === 'transcribing';
            const isStreaming = brainState === 'streaming';
            const isSpeaking = brainState === 'speaking';
            const statePace =
                isThinking
                    ? 1.38
                    : isStreaming
                    ? 1.28
                    : isSpeaking
                    ? 1.25 + energySmooth * 0.65
                    : isListening
                    ? 1.05 + energySmooth * 0.55
                    : 0.85;

            simT += dt * statePace;

            // In Live Mode, spoken voice peaks gently radiate concentric acoustic waves from center
            if ((isListening || isSpeaking) && energySmooth > 0.16 && simT - lastVoiceRippleT > 0.28) {
                lastVoiceRippleT = simT;
                spawnRipple(0, 0, {
                    amp: Math.min(0.32, 0.12 + energySmooth * 0.24),
                    speed: isSpeaking ? 2.15 : 1.85,
                    width: 0.46,
                    life: 1.75,
                    ember: isSpeaking ? 1.15 : 0.9,
                });
            }

            // Prune expired effects
            for (let i = ripples.length - 1; i >= 0; i--) {
                if (simT - ripples[i].birth > ripples[i].life) ripples.splice(i, 1);
            }
            for (let i = plucks.length - 1; i >= 0; i--) {
                if (simT - plucks[i].birth > plucks[i].life) plucks.splice(i, 1);
            }
            for (let i = scans.length - 1; i >= 0; i--) {
                if (simT - scans[i].birth > scans[i].life) scans.splice(i, 1);
            }
            for (let i = sparks.length - 1; i >= 0; i--) {
                const sp = sparks[i];
                if (simT - sp.birth > sp.life) {
                    sparks.splice(i, 1);
                } else {
                    sp.col += sp.vx * dt;
                    sp.row += sp.vy * dt;
                    sp.vy *= Math.pow(0.28, dt); // smooth upward air drag
                }
            }

            zBuf.fill(0);
            charBuf.fill(0);

            const pxW = cols * cellW;
            const pxH = rows * cellH;
            const spanPx = Math.max(pxW * 0.48, pxH * 0.78);
            const camDist = 2.65;
            const fovX = (spanPx * 1.15) / cellW;
            const fovY = (spanPx * 1.15) / cellH;
            const cx = cols * 0.5;
            const cy = rows * 0.55;

            const pitch = 0.62 - pointer.y * 0.14 + Math.sin(simT * 0.18) * 0.03;
            const yaw = Math.sin(simT * 0.16) * 0.14 + pointer.x * 0.24;
            const cP = Math.cos(pitch);
            const sP = Math.sin(pitch);
            const cY = Math.cos(yaw);
            const sY = Math.sin(yaw);

            const cursorWX = pointer.x * 2.15;
            const cursorWZ = pointer.y * 1.45;
            const cursorBoost = pointer.active ? (0.30 + pointer.speed * 0.18) : 0;

            const gxCount = cols < 90 ? 58 : 88;
            const gzCount = rows < 36 ? 34 : 50;
            const worldSpanX = 4.6;
            const worldSpanZ = 3.2;
            const baseAmp = 0.30 + energySmooth * 0.34 + (isThinking || isStreaming ? 0.10 : 0);

            for (let zi = 0; zi < gzCount; zi++) {
                const vz = (zi / (gzCount - 1) - 0.5) * worldSpanZ;
                for (let xi = 0; xi < gxCount; xi++) {
                    const vx = (xi / (gxCount - 1) - 0.5) * worldSpanX;
                    const distCenter = Math.hypot(vx * 0.85, vz);

                    // 1. Base organic 3D topographic wave field
                    const w1 = Math.sin(distCenter * 3.8 - simT * 2.1) * Math.exp(-distCenter * 0.34);
                    const w2 = Math.sin(vx * 1.9 + simT * 0.95) * Math.cos(vz * 1.85 - simT * 0.78) * 0.58;
                    const w3 = Math.cos((vx - vz) * 1.35 + simT * 0.65) * 0.24;
                    let vy = (w1 + w2 + w3) * baseAmp - 0.18;

                    let hotBoost = flowGlow * 0.06;

                    // 2. Silky magnetic cursor crest under mouse pointer
                    if (cursorBoost > 0.01) {
                        const cdx = vx - cursorWX;
                        const cdz = vz - cursorWZ;
                        const cDist2 = cdx * cdx + cdz * cdz;
                        if (cDist2 < 1.35) {
                            const gauss = Math.exp(-cDist2 * 2.4);
                            vy += gauss * cursorBoost;
                            hotBoost += gauss * (0.45 + pointer.speed * 0.35);
                        }
                    }

                    // 3. Mouse click & wake ripples
                    for (let r = 0; r < ripples.length; r++) {
                        const rp = ripples[r];
                        const age = simT - rp.birth;
                        const decay = 1 - age / rp.life;
                        if (decay <= 0) continue;
                        const rDist = Math.hypot(vx - rp.wx, vz - rp.wz);
                        const radius = age * rp.speed;
                        const delta = rDist - radius;
                        if (Math.abs(delta) < rp.width * 2.5) {
                            const env = Math.exp(-(delta * delta) / (rp.width * rp.width)) * decay * decay;
                            vy += Math.cos((delta / rp.width) * 2.4) * env * rp.amp;
                            hotBoost += env * rp.ember * 0.8;
                        }
                    }

                    // 4. Tactile QWERTY string-plucks: directional traveling wave along that key's column!
                    for (let p = 0; p < plucks.length; p++) {
                        const pk = plucks[p];
                        const age = simT - pk.birth;
                        const decay = 1 - age / pk.life;
                        if (decay <= 0) continue;
                        const dx = vx - pk.wx;
                        if (Math.abs(dx) > pk.sigmaX * 2.6) continue;
                        const envX = Math.exp(-(dx * dx) / (pk.sigmaX * pk.sigmaX));
                        // Wave glides smoothly along Z from the key's depth forward & back
                        const travelZ = pk.wz - age * 1.45;
                        const dz = vz - travelZ;
                        const envZ = Math.exp(-(dz * dz) / 0.55);
                        const osc = Math.cos(age * pk.freq - Math.abs(dz) * 3.0);
                        const env = envX * envZ * decay * decay;
                        vy += (0.55 + 0.45 * osc) * env * pk.amp;
                        hotBoost += env * pk.ember * 0.95;
                    }

                    // 5. Enter / Send transmission scanline sweep across the full mountain horizon
                    for (let s = 0; s < scans.length; s++) {
                        const sc = scans[s];
                        const progress = (simT - sc.birth) / sc.life;
                        if (progress < 0 || progress > 1) continue;
                        const scanZ = sc.startZ + (sc.endZ - sc.startZ) * progress;
                        const dz = vz - scanZ;
                        if (Math.abs(dz) < sc.width * 2.8) {
                            const env = Math.exp(-(dz * dz) / (sc.width * sc.width)) * Math.sin(progress * Math.PI);
                            vy += env * sc.amp;
                            hotBoost += env * 1.15;
                        }
                    }

                    const x1 = vx * cY + vz * sY;
                    const z1 = -vx * sY + vz * cY;
                    const y2 = vy * cP - z1 * sP;
                    const z2 = vy * sP + z1 * cP;

                    const elev = Math.max(0, Math.min(1, (vy + 0.56) / 0.92));
                    const heat = Math.min(1, elev * 0.72 + hotBoost * 0.8);
                    const isEmberRidge = elev > 0.56 || hotBoost > 0.24;

                    let colorIdx;
                    if (isEmberRidge) {
                        const emberLevel = Math.max(0, Math.min(1, (heat - 0.40) / 0.60));
                        colorIdx = 9 + Math.min(6, Math.floor(emberLevel * 6.9));
                    } else {
                        colorIdx = Math.min(6, Math.floor(elev * 8.2));
                    }

                    let chCode;
                    if (elev > 0.86 || hotBoost > 0.78) chCode = 94; // '^'
                    else if (elev > 0.70 || hotBoost > 0.44) chCode = 47; // '/'
                    else if (elev > 0.54 || hotBoost > 0.24) chCode = 61; // '='
                    else if (elev > 0.38) chCode = 45; // '-'
                    else if (elev > 0.23) chCode = 58; // ':'
                    else chCode = 46; // '.'

                    plot(x1, y2, z2, chCode, colorIdx, camDist, fovX, fovY, cx, cy);
                }
            }

            // Overlay delicate rising typed-character sparks (char -> '*' -> '+' -> '·')
            for (let i = 0; i < sparks.length; i++) {
                const sp = sparks[i];
                const ageFrac = (simT - sp.birth) / sp.life;
                const sc = Math.round(sp.col);
                const sr = Math.round(sp.row);
                if (sc < 1 || sc >= cols - 1 || sr < 1 || sr >= rows - 1) continue;
                const idx = sr * cols + sc;
                let ch = sp.charCode;
                let colIdx = 15;
                if (ageFrac > 0.72) {
                    ch = 183; // '·'
                    colIdx = 9;
                } else if (ageFrac > 0.48) {
                    ch = 43; // '+'
                    colIdx = 12;
                } else if (ageFrac > 0.25) {
                    ch = 42; // '*'
                    colIdx = 14;
                }
                charBuf[idx] = ch;
                colorBuf[idx] = colIdx;
                zBuf[idx] = 10;
            }

            // Subtle architectural coordinate '+' markers in open sky
            const stepX = 10;
            const stepY = 5;
            for (let r = 1; r < rows - 1; r += stepY) {
                for (let c = 3; c < cols - 3; c += stepX) {
                    const idx = r * cols + c;
                    if (charBuf[idx] !== 0) continue;
                    const wave = Math.sin(c * 0.06 + r * 0.14 - simT * 1.1);
                    if (wave > 0.65 - flowGlow * 0.25) {
                        charBuf[idx] = 43; // '+'
                        colorBuf[idx] = wave > 0.86 ? 18 : 17;
                        zBuf[idx] = 0.01;
                    } else {
                        charBuf[idx] = 183; // '·'
                        colorBuf[idx] = 16;
                        zBuf[idx] = 0.005;
                    }
                }
            }

            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.fillStyle = '#050505';
            ctx.fillRect(0, 0, canvas.width / dpr, canvas.height / dpr);

            ctx.font = `500 ${fontSize}px "JetBrains Mono", "Cascadia Code", "Fira Code", Consolas, monospace`;
            ctx.textBaseline = 'top';

            for (let b = 0; b < PALETTE.length; b++) {
                bucketIndices[b].length = 0;
            }

            const totalCells = cols * rows;
            for (let i = 0; i < totalCells; i++) {
                if (charBuf[i] !== 0) {
                    bucketIndices[colorBuf[i]].push(i);
                }
            }

            const offsetX = ((canvas.width / dpr) - cols * cellW) * 0.5;
            const offsetY = ((canvas.height / dpr) - rows * cellH) * 0.5;

            for (let b = 0; b < PALETTE.length; b++) {
                const list = bucketIndices[b];
                if (list.length === 0) continue;
                ctx.fillStyle = PALETTE[b];
                for (let k = 0; k < list.length; k++) {
                    const idx = list[k];
                    const r = (idx / cols) | 0;
                    const c = idx - r * cols;
                    ctx.fillText(String.fromCharCode(charBuf[idx]), offsetX + c * cellW, offsetY + r * cellH);
                }
            }
        };

        rafId = requestAnimationFrame(animate);

        return () => {
            cancelAnimationFrame(rafId);
            resizeObserver.disconnect();
            document.removeEventListener('visibilitychange', onVisibility);
            window.removeEventListener('pointermove', onWindowPointerMove);
            document.removeEventListener('pointerleave', onWindowPointerLeave);
            window.removeEventListener('pointerdown', onWindowPointerDown);
            window.removeEventListener('spidey:keystroke', onKeystroke);
            window.removeEventListener('spidey:submit_wave', onSubmitWave);
        };
    }, []);

    return (
        <div
            ref={containerRef}
            aria-hidden="true"
            className={`pointer-events-none fixed inset-0 z-0 overflow-hidden bg-[#050505] select-none ${className}`}
        >
            <canvas ref={canvasRef} className="block h-full w-full" />
        </div>
    );
}
