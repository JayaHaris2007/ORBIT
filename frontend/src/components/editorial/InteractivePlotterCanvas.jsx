import { useEffect, useRef } from 'react';
import { useSpideyBrain } from '../../context/SpideyBrainContext';

/**
 * Fixed interactive architectural pen-plotter background:
 * 1. 1px structural hairline grid + '+' registration crosses
 * 2. Magnetic grid-node drafting ticks turning toward the cursor
 * 3. Architectural Spider Web geometry (radial anchor spokes + concentric catenary silk arcs + node ticks):
 *    - Pen-plotter draw-in from hub outward on load
 *    - Spring-elastic silk deflection near cursor + snap silk thread to nearest web node
 *    - Traveling square signal ticks gliding along spokes (reacts to AI state)
 *    - Click-triggered web pluck & compass shockwave ripples
 */
export default function InteractivePlotterCanvas() {
    const canvasRef = useRef(null);
    const coordRef = useRef(null);
    const brain = useSpideyBrain();

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return undefined;

        const ctx = canvas.getContext('2d');
        if (!ctx) return undefined;

        const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        const GRID_SIZE = 64;
        const CURSOR_RADIUS = 185;
        const SPOKE_COUNT = 14;
        const RING_RADII = [58, 108, 168, 238, 320, 415, 525, 650, 790, 950];

        let width = window.innerWidth;
        let height = window.innerHeight;
        let dpr = Math.min(window.devicePixelRatio || 1, 1.5);
        let gridNodes = [];
        let webHub = { x: 0, y: 0 };
        let webSpokes = [];
        let webRings = [];
        let ripples = [];
        let drawProgress = prefersReducedMotion ? 1 : 0;

        const mouse = {
            x: -9999,
            y: -9999,
            targetX: -9999,
            targetY: -9999,
            active: false,
        };

        const buildGeometry = () => {
            width = window.innerWidth;
            height = window.innerHeight;
            dpr = Math.min(window.devicePixelRatio || 1, 1.5);

            canvas.width = Math.floor(width * dpr);
            canvas.height = Math.floor(height * dpr);
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;

            // 1. Magnetic grid ticks
            const cols = Math.ceil(width / GRID_SIZE);
            const rows = Math.ceil(height / GRID_SIZE);
            const offsetX = (width - cols * GRID_SIZE) * 0.5;
            const offsetY = (height - rows * GRID_SIZE) * 0.5;
            gridNodes = [];
            for (let i = 0; i <= cols; i++) {
                for (let j = 0; j <= rows; j++) {
                    const x = Math.round(offsetX + i * GRID_SIZE) + 0.5;
                    const y = Math.round(offsetY + j * GRID_SIZE) + 0.5;
                    const restAngle = Math.sin(i * 0.35 + j * 0.25) * 0.45 - Math.PI * 0.25;
                    gridNodes.push({
                        x,
                        y,
                        i,
                        j,
                        angle: restAngle,
                        restAngle,
                        length: 6.5,
                        energy: 0,
                    });
                }
            }

            // 2. Architectural Spider Web centered asymmetrically in Swiss print composition
            webHub = {
                x: width * 0.72,
                y: height * 0.28,
            };
            const maxSpan = Math.hypot(width, height) * 1.05;

            webSpokes = [];
            for (let s = 0; s < SPOKE_COUNT; s++) {
                // Slight organic angular offset while preserving architectural balance
                const angle = (s / SPOKE_COUNT) * Math.PI * 2 + Math.sin(s * 1.7) * 0.035;
                const cos = Math.cos(angle);
                const sin = Math.sin(angle);
                webSpokes.push({
                    angle,
                    cos,
                    sin,
                    endX: webHub.x + cos * maxSpan,
                    endY: webHub.y + sin * maxSpan,
                    accent: s % 3 === 0,
                    pulseT: (s * 0.23) % 1,
                    pulseSpeed: 0.08 + (s % 4) * 0.02,
                });
            }

            // Concentric polygonal catenary silk rings anchored to spoke nodes
            webRings = RING_RADII.map((radius, rIdx) => {
                const nodes = webSpokes.map((sp, sIdx) => {
                    // Subtle radial variation per spoke for organic web precision
                    const rLocal = radius * (1 + Math.sin(sIdx * 2.1 + rIdx * 0.8) * 0.03);
                    const bx = webHub.x + sp.cos * rLocal;
                    const by = webHub.y + sp.sin * rLocal;
                    return {
                        baseX: bx,
                        baseY: by,
                        x: bx,
                        y: by,
                        vx: 0,
                        vy: 0,
                        nx: sp.cos,
                        ny: sp.sin,
                        rLocal,
                        isSquare: (sIdx + rIdx) % 2 === 0,
                    };
                });

                return {
                    radius,
                    accent: rIdx === 1 || rIdx === 4 || rIdx === 7,
                    stagger: 0.14 + rIdx * 0.075,
                    nodes,
                };
            });
        };

        const onPointerMove = (e) => {
            mouse.targetX = e.clientX;
            mouse.targetY = e.clientY;
            mouse.active = true;
            if (coordRef.current) {
                const cx = String(Math.round(e.clientX)).padStart(4, '0');
                const cy = String(Math.round(e.clientY)).padStart(4, '0');
                coordRef.current.textContent = `X ${cx} · Y ${cy}`;
                coordRef.current.style.opacity = '1';
            }
        };

        const onPointerLeave = () => {
            mouse.active = false;
            mouse.targetX = -9999;
            mouse.targetY = -9999;
            if (coordRef.current) {
                coordRef.current.style.opacity = '0.4';
            }
        };

        const onPointerDown = (e) => {
            if (prefersReducedMotion) return;
            ripples.push({
                x: e.clientX,
                y: e.clientY,
                radius: 10,
                maxRadius: Math.max(width, height) * 0.55,
                alpha: 0.58,
            });
            if (ripples.length > 4) ripples.shift();
        };

        window.addEventListener('resize', buildGeometry);
        window.addEventListener('pointermove', onPointerMove, { passive: true });
        window.addEventListener('pointerleave', onPointerLeave, { passive: true });
        window.addEventListener('pointerdown', onPointerDown, { passive: true });

        buildGeometry();

        let rafId = 0;
        let lastTime = performance.now();
        let simTime = 0;
        let lastPulseTime = 0;
        let hubSignalTimer = 1.6;
        const HUB_SIGNAL_INTERVAL = 2.0;

        const isLightTheme = () => document.documentElement.querySelector('.app-theme-light') !== null;

        const render = (now) => {
            rafId = requestAnimationFrame(render);
            if (document.hidden) {
                lastTime = now;
                return;
            }

            const dt = Math.min((now - lastTime) / 1000, 0.05);
            lastTime = now;

            if (!prefersReducedMotion) {
                simTime += dt;
                if (drawProgress < 1.35) {
                    drawProgress = Math.min(1.35, drawProgress + dt * 0.85);
                }
            }

            const ctxPulse = brain?.pulseRef?.current;
            if (!prefersReducedMotion && ctxPulse && ctxPulse.time > lastPulseTime) {
                lastPulseTime = ctxPulse.time;
                ripples.push({
                    x: webHub.x,
                    y: webHub.y,
                    radius: 14,
                    maxRadius: Math.max(width, height) * 0.72,
                    alpha: 0.45,
                    speed: 440,
                    fromHub: true,
                });
                if (ripples.length > 6) ripples.shift();
            }

            // Continuous 2-second signal pulse emitted from the center of the spider web
            if (!prefersReducedMotion && drawProgress >= 0.85) {
                hubSignalTimer += dt;
                if (hubSignalTimer >= HUB_SIGNAL_INTERVAL) {
                    hubSignalTimer -= HUB_SIGNAL_INTERVAL;
                    ripples.push({
                        x: webHub.x,
                        y: webHub.y,
                        radius: 12,
                        maxRadius: Math.max(width, height) * 0.78,
                        alpha: 0.55,
                        speed: 360,
                        fromHub: true,
                    });
                    if (ripples.length > 6) ripples.shift();
                }
            }

            if (mouse.active) {
                mouse.x += (mouse.targetX - mouse.x) * Math.min(1, dt * 14);
                mouse.y += (mouse.targetY - mouse.y) * Math.min(1, dt * 14);
            } else {
                mouse.x = -9999;
                mouse.y = -9999;
            }

            for (let r = ripples.length - 1; r >= 0; r--) {
                const rp = ripples[r];
                rp.radius += dt * (rp.speed || 440);
                rp.alpha *= Math.pow(rp.fromHub ? 0.42 : 0.24, dt);
                if (rp.radius >= rp.maxRadius || rp.alpha < 0.02) {
                    ripples.splice(r, 1);
                }
            }

            const light = isLightTheme();
            const gridStroke = light ? 'rgba(20, 19, 17, 0.05)' : 'rgba(242, 239, 233, 0.036)';
            const crossStroke = light ? 'rgba(20, 19, 17, 0.11)' : 'rgba(242, 239, 233, 0.09)';
            const baseRgb = light ? '20, 19, 17' : '242, 239, 233';
            const orangeRgb = '217, 93, 36';

            const aiState = brain?.brainStateRef?.current || 'idle';
            const aiActive = aiState !== 'idle';
            const speedMult = aiState === 'thinking' || aiState === 'streaming' ? 2.4 : aiActive ? 1.65 : 1;

            ctx.save();
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, width, height);

            // 1. Fixed 1px Hairline Structural Grid + Registration Crosses
            const cols = Math.ceil(width / GRID_SIZE);
            const rows = Math.ceil(height / GRID_SIZE);
            const offsetX = (width - cols * GRID_SIZE) * 0.5;
            const offsetY = (height - rows * GRID_SIZE) * 0.5;

            ctx.strokeStyle = gridStroke;
            ctx.lineWidth = 1;
            ctx.beginPath();
            for (let i = 0; i <= cols; i++) {
                const x = Math.round(offsetX + i * GRID_SIZE) + 0.5;
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height);
            }
            for (let j = 0; j <= rows; j++) {
                const y = Math.round(offsetY + j * GRID_SIZE) + 0.5;
                ctx.moveTo(0, y);
                ctx.lineTo(width, y);
            }
            ctx.stroke();

            ctx.strokeStyle = crossStroke;
            ctx.beginPath();
            for (let i = 0; i <= cols; i += 2) {
                for (let j = 0; j <= rows; j += 2) {
                    const x = Math.round(offsetX + i * GRID_SIZE) + 0.5;
                    const y = Math.round(offsetY + j * GRID_SIZE) + 0.5;
                    ctx.moveTo(x - 3, y);
                    ctx.lineTo(x + 3, y);
                    ctx.moveTo(x, y - 3);
                    ctx.lineTo(x, y + 3);
                }
            }
            ctx.stroke();

            // 2. Magnetic Grid-Node Drafting Ticks Turning Toward Cursor
            const tickLerp = prefersReducedMotion ? 1 : Math.min(1, dt * 11);
            for (let n = 0; n < gridNodes.length; n++) {
                const node = gridNodes[n];
                const flowAngle =
                    node.restAngle +
                    (prefersReducedMotion
                        ? 0
                        : Math.sin(simTime * (aiActive ? 1.4 : 0.55) + node.i * 0.4 + node.j * 0.3) * 0.25);

                let targetAngle = flowAngle;
                let targetLen = 6.5;
                let targetEnergy = aiActive ? 0.2 : 0;

                if (mouse.active) {
                    const dx = mouse.x - node.x;
                    const dy = mouse.y - node.y;
                    const dist = Math.hypot(dx, dy);
                    if (dist < CURSOR_RADIUS) {
                        const factor = 1 - dist / CURSOR_RADIUS;
                        targetAngle = Math.atan2(dy, dx);
                        targetLen = 6.5 + factor * 7.5;
                        targetEnergy = Math.max(targetEnergy, factor);
                    }
                }

                for (let r = 0; r < ripples.length; r++) {
                    const rp = ripples[r];
                    const dx = node.x - rp.x;
                    const dy = node.y - rp.y;
                    const dist = Math.hypot(dx, dy);
                    const band = Math.abs(dist - rp.radius);
                    if (band < 42) {
                        const waveForce = (1 - band / 42) * rp.alpha * 1.8;
                        targetAngle = Math.atan2(dy, dx);
                        targetLen = Math.max(targetLen, 6.5 + waveForce * 7);
                        targetEnergy = Math.max(targetEnergy, Math.min(1, waveForce));
                    }
                }

                let diff = targetAngle - node.angle;
                while (diff < -Math.PI) diff += Math.PI * 2;
                while (diff > Math.PI) diff -= Math.PI * 2;
                node.angle += diff * tickLerp;
                node.length += (targetLen - node.length) * tickLerp;
                node.energy += (targetEnergy - node.energy) * tickLerp;

                const x2 = node.x + Math.cos(node.angle) * node.length;
                const y2 = node.y + Math.sin(node.angle) * node.length;

                if (node.energy > 0.12) {
                    const alpha = Math.min(0.85, 0.16 + node.energy * 0.65);
                    ctx.strokeStyle = `rgba(${orangeRgb}, ${alpha.toFixed(3)})`;
                } else {
                    ctx.strokeStyle = `rgba(${baseRgb}, 0.13)`;
                }
                ctx.lineWidth = node.energy > 0.35 ? 1.25 : 0.9;
                ctx.beginPath();
                ctx.moveTo(node.x, node.y);
                ctx.lineTo(x2, y2);
                ctx.stroke();
            }

            // 3. Architectural Spider Web — Radial Anchor Spokes
            const spokeProgress = Math.min(1, drawProgress * 1.45);
            for (let s = 0; s < webSpokes.length; s++) {
                const sp = webSpokes[s];
                if (!prefersReducedMotion) {
                    sp.pulseT = (sp.pulseT + dt * sp.pulseSpeed * speedMult) % 1;
                }

                // Check if cursor is near this spoke ray for subtle highlight
                let spokeProximity = 0;
                if (mouse.active) {
                    const mx = mouse.x - webHub.x;
                    const my = mouse.y - webHub.y;
                    const proj = mx * sp.cos + my * sp.sin;
                    if (proj > 0) {
                        const perpDist = Math.abs(-mx * sp.sin + my * sp.cos);
                        if (perpDist < 90) {
                            spokeProximity = 1 - perpDist / 90;
                        }
                    }
                }

                const ex = webHub.x + (sp.endX - webHub.x) * spokeProgress;
                const ey = webHub.y + (sp.endY - webHub.y) * spokeProgress;

                const alpha = (sp.accent ? 0.14 : 0.07) + spokeProximity * 0.28;
                ctx.strokeStyle =
                    sp.accent || spokeProximity > 0.3
                        ? `rgba(${orangeRgb}, ${alpha.toFixed(3)})`
                        : `rgba(${baseRgb}, ${alpha.toFixed(3)})`;
                ctx.lineWidth = spokeProximity > 0.35 ? 1.2 : 0.9;

                ctx.beginPath();
                ctx.moveTo(webHub.x, webHub.y);
                ctx.lineTo(ex, ey);
                ctx.stroke();

                // Traveling square signal tick moving outward along spoke
                if (spokeProgress >= 0.95 && !prefersReducedMotion && s % 2 === 0) {
                    const travelDist = 45 + sp.pulseT * 640;
                    const px = webHub.x + sp.cos * travelDist;
                    const py = webHub.y + sp.sin * travelDist;
                    if (px >= -10 && px <= width + 10 && py >= -10 && py <= height + 10) {
                        ctx.fillStyle = sp.accent
                            ? `rgba(${orangeRgb}, 0.72)`
                            : `rgba(${baseRgb}, 0.38)`;
                        ctx.fillRect(px - 1.75, py - 1.75, 3.5, 3.5);
                    }
                }
            }

            // Web Hub Registration Target (inner burnt-orange dot + hairline ring)
            ctx.strokeStyle = `rgba(${orangeRgb}, 0.35)`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(webHub.x, webHub.y, 12, 0, Math.PI * 2 * spokeProgress);
            ctx.stroke();
            ctx.fillStyle = `rgba(${orangeRgb}, 0.65)`;
            ctx.beginPath();
            ctx.arc(webHub.x, webHub.y, 3, 0, Math.PI * 2);
            ctx.fill();

            // 4. Concentric Catenary Silk Rings + Continuous Hub Signal Response
            const springK = 95;
            const damping = 9.0;

            for (let rIdx = 0; rIdx < webRings.length; rIdx++) {
                const ring = webRings[rIdx];
                const ringDraw = Math.max(0, Math.min(1, (drawProgress - ring.stagger) * 1.4));
                const nodes = ring.nodes;
                let ringMaxProx = 0;
                let ringSignalBoost = 0;

                // Measure how strongly a hub signal wave is currently crossing this ring
                for (let r = 0; r < ripples.length; r++) {
                    const rp = ripples[r];
                    if (!rp.fromHub) continue;
                    const band = Math.abs(ring.radius - rp.radius);
                    if (band < 48) {
                        ringSignalBoost = Math.max(ringSignalBoost, (1 - band / 48) * rp.alpha * 1.35);
                    }
                }

                // Update spring-physics displacement for each junction node
                for (let s = 0; s < nodes.length; s++) {
                    const nd = nodes[s];
                    let targetX = nd.baseX;
                    let targetY = nd.baseY;

                    if (!prefersReducedMotion) {
                        const breathe =
                            Math.sin(simTime * (aiActive ? 1.7 : 0.7) + rIdx * 0.7 + s * 0.4) *
                            (aiActive ? 3.5 : 1.6);
                        targetX += nd.nx * breathe;
                        targetY += nd.ny * breathe;
                    }

                    if (mouse.active) {
                        const dx = nd.baseX - mouse.x;
                        const dy = nd.baseY - mouse.y;
                        const dist = Math.hypot(dx, dy);
                        if (dist < CURSOR_RADIUS) {
                            const prox = 1 - dist / CURSOR_RADIUS;
                            ringMaxProx = Math.max(ringMaxProx, prox);
                            const pull = Math.pow(prox, 1.4) * 22;
                            const inv = dist > 0.001 ? 1 / dist : 0;
                            targetX += dx * inv * pull;
                            targetY += dy * inv * pull;
                        }
                    }

                    for (let r = 0; r < ripples.length; r++) {
                        const rp = ripples[r];
                        const dx = nd.baseX - rp.x;
                        const dy = nd.baseY - rp.y;
                        const dist = Math.hypot(dx, dy);
                        const band = Math.abs(dist - rp.radius);
                        if (band < 55) {
                            const wave = (1 - band / 55) * rp.alpha * (rp.fromHub ? 12 : 18);
                            const inv = dist > 0.001 ? 1 / dist : 0;
                            targetX += dx * inv * wave;
                            targetY += dy * inv * wave;
                        }
                    }

                    const fx = (targetX - nd.x) * springK;
                    const fy = (targetY - nd.y) * springK;
                    const decay = Math.exp(-damping * dt);
                    nd.vx = (nd.vx + fx * dt) * decay;
                    nd.vy = (nd.vy + fy * dt) * decay;
                    nd.x += nd.vx * dt;
                    nd.y += nd.vy * dt;
                }

                if (ringDraw <= 0.02) continue;

                const segCount = Math.ceil(nodes.length * ringDraw);
                const baseAlpha = ring.accent ? 0.2 : 0.09;
                const activeAlpha = Math.min(0.8, baseAlpha + ringMaxProx * 0.4 + ringSignalBoost * 0.55);
                ctx.strokeStyle =
                    ring.accent || ringMaxProx > 0.35 || ringSignalBoost > 0.15
                        ? `rgba(${orangeRgb}, ${activeAlpha.toFixed(3)})`
                        : `rgba(${baseRgb}, ${activeAlpha.toFixed(3)})`;
                ctx.lineWidth = ringMaxProx > 0.35 || ringSignalBoost > 0.2 || ring.accent ? 1.2 : 0.9;

                // Draw catenary inward-curving silk arcs between spoke junctions
                ctx.beginPath();
                for (let s = 0; s < segCount; s++) {
                    const a = nodes[s];
                    const b = nodes[(s + 1) % nodes.length];

                    const midX = (a.x + b.x) * 0.5;
                    const midY = (a.y + b.y) * 0.5;
                    const ctrlX = midX + (webHub.x - midX) * 0.11;
                    const ctrlY = midY + (webHub.y - midY) * 0.11;

                    const isLastPartial = s === segCount - 1 && ringDraw < 1;
                    const segFrac = isLastPartial ? (ringDraw * nodes.length) % 1 || 1 : 1;

                    ctx.moveTo(a.x, a.y);
                    if (segFrac < 0.99) {
                        const px = (1 - segFrac) * (1 - segFrac) * a.x + 2 * (1 - segFrac) * segFrac * ctrlX + segFrac * segFrac * b.x;
                        const py = (1 - segFrac) * (1 - segFrac) * a.y + 2 * (1 - segFrac) * segFrac * ctrlY + segFrac * segFrac * b.y;
                        const qx = a.x + (ctrlX - a.x) * segFrac;
                        const qy = a.y + (ctrlY - a.y) * segFrac;
                        ctx.quadraticCurveTo(qx, qy, px, py);
                    } else {
                        ctx.quadraticCurveTo(ctrlX, ctrlY, b.x, b.y);
                    }
                }
                ctx.stroke();

                // Small geometric node ticks at intersections on highlighted/accent/signal-lit rings
                if (ringDraw > 0.9 && (ring.accent || ringMaxProx > 0.25 || ringSignalBoost > 0.12)) {
                    const nodeAlpha = Math.min(0.9, 0.35 + ringSignalBoost * 0.65);
                    for (let s = 0; s < nodes.length; s++) {
                        const nd = nodes[s];
                        if (nd.x < -10 || nd.x > width + 10 || nd.y < -10 || nd.y > height + 10) continue;
                        ctx.fillStyle =
                            ring.accent || ringSignalBoost > 0.12
                                ? `rgba(${orangeRgb}, ${nodeAlpha.toFixed(3)})`
                                : `rgba(${baseRgb}, 0.3)`;
                        if (nd.isSquare) {
                            ctx.fillRect(nd.x - 1.5, nd.y - 1.5, 3, 3);
                        } else {
                            ctx.beginPath();
                            ctx.arc(nd.x, nd.y, 1.5, 0, Math.PI * 2);
                            ctx.fill();
                        }
                    }
                }
            }

            // 5. Expanding Signal & Click Ripples
            for (let r = 0; r < ripples.length; r++) {
                const rp = ripples[r];
                ctx.strokeStyle = `rgba(${orangeRgb}, ${rp.alpha.toFixed(3)})`;
                ctx.lineWidth = rp.fromHub ? 1.15 : 1;
                ctx.beginPath();
                ctx.arc(rp.x, rp.y, rp.radius, 0, Math.PI * 2);
                ctx.stroke();
            }

            ctx.restore();
        };

        rafId = requestAnimationFrame(render);

        return () => {
            cancelAnimationFrame(rafId);
            window.removeEventListener('resize', buildGeometry);
            window.removeEventListener('pointermove', onPointerMove);
            window.removeEventListener('pointerleave', onPointerLeave);
            window.removeEventListener('pointerdown', onPointerDown);
        };
    }, [brain]);

    return (
        <>
            <canvas
                ref={canvasRef}
                aria-hidden="true"
                className="pointer-events-none fixed inset-0 z-0"
            />
            <div
                ref={coordRef}
                aria-hidden="true"
                className="pointer-events-none fixed bottom-3 left-3 z-20 hidden border border-[#F2EFE9]/15 bg-[#111111]/90 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.18em] text-[#9C968E] transition-opacity duration-200 md:left-[272px] md:block"
                style={{ opacity: 0.4 }}
            >
                X 0000 · Y 0000
            </div>
        </>
    );
}
