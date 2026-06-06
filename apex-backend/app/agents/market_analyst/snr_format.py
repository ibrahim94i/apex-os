"""Format SNR levels for market analyst prompt (informational only)."""

from app.schemas.snr import SNRSnapshotSchema


def snr_block_from_snapshot(snr: SNRSnapshotSchema | None) -> str:
    if snr is None:
        return ""

    def _fmt(level: float | None, label: str) -> str:
        return f"{label}: {level:.2f}" if level is not None else f"{label}: —"

    lines = [
        _fmt(snr.support_1, "دعم 1 (S1)"),
        _fmt(snr.support_2, "دعم 2 (S2)"),
        _fmt(snr.support_3, "دعم 3 (S3)"),
        _fmt(snr.resistance_1, "مقاومة 1 (R1)"),
        _fmt(snr.resistance_2, "مقاومة 2 (R2)"),
        _fmt(snr.resistance_3, "مقاومة 3 (R3)"),
    ]
    dist_s = f"{snr.distance_to_support_pct:.2f}%" if snr.distance_to_support_pct is not None else "—"
    dist_r = f"{snr.distance_to_resistance_pct:.2f}%" if snr.distance_to_resistance_pct is not None else "—"
    lines.append(f"المسافة إلى أقرب دعم: {dist_s}")
    lines.append(f"المسافة إلى أقرب مقاومة: {dist_r}")
    return "\nمستويات الدعم/المقاومة (SNR — Pivot H/L):\n" + "\n".join(f"- {line}" for line in lines)
