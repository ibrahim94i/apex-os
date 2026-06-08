"""Format SNR level zones for market analyst prompt (informational only)."""

from app.schemas.snr import SNRLevelZone, SNRSnapshotSchema


def _fmt_zone(label: str, zone: SNRLevelZone | None) -> str | None:
    if zone is None:
        return None
    return f"{label}: {zone.level:.2f} (منطقة {zone.low:.2f} – {zone.high:.2f})"


def snr_block_from_snapshot(snr: SNRSnapshotSchema | None) -> str:
    if snr is None:
        return ""
    lines = [
        _fmt_zone("دعم 1 (S1)", snr.support_1_zone),
        _fmt_zone("دعم 2 (S2)", snr.support_2_zone),
        _fmt_zone("دعم 3 (S3)", snr.support_3_zone),
        _fmt_zone("مقاومة 1 (R1)", snr.resistance_1_zone),
        _fmt_zone("مقاومة 2 (R2)", snr.resistance_2_zone),
        _fmt_zone("مقاومة 3 (R3)", snr.resistance_3_zone),
    ]
    lines = [line for line in lines if line]
    dist_s = f"{snr.distance_to_support_pct:.2f}%" if snr.distance_to_support_pct is not None else "—"
    dist_r = f"{snr.distance_to_resistance_pct:.2f}%" if snr.distance_to_resistance_pct is not None else "—"
    lines.append(f"المسافة إلى S1: {dist_s} | إلى R1: {dist_r}")
    lines.append("كل مستوى = منطقة ±0.25% — السعر داخل المنطقة = انتظار")
    return "\nمستويات الدعم/المقاومة (SNR — Pivot H/L):\n" + "\n".join(f"- {line}" for line in lines)
