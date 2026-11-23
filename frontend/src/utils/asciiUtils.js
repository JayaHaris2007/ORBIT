export function buildAsciiBar(percent, width = 12) {
    const clamped = Math.max(0, Math.min(100, Number(percent) || 0));
    const filled = Math.round((clamped / 100) * width);
    return `${'█'.repeat(filled)}${'░'.repeat(Math.max(0, width - filled))}`;
}
