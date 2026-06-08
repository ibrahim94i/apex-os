"""SNR soft-penalty messaging — no hard-block text in UI/Telegram."""

from app.services.signal_rejection_i18n import (
    SNR_INSIDE_ZONE_WARNING_AR,
    is_snr_hard_block_message,
    normalize_snr_consensus_fields,
    rejection_reason_ar,
)


def test_snr_zone_block_not_shown_as_rejection() -> None:
    assert rejection_reason_ar("SNR Zone Block") is None


def test_legacy_snr_codes_not_shown_as_rejection() -> None:
    for code in (
        "snr_in_r1_zone",
        "snr_in_level_zone",
        "snr_awaiting_breakout",
        "WAIT",
    ):
        assert rejection_reason_ar(code) is None


def test_normalize_maps_legacy_veto_to_warning() -> None:
    rr, rr_ar, warning = normalize_snr_consensus_fields(
        rejection_reason="SNR Zone Block",
        rejection_reason_ar="انتظار — SNR Zone Block (فيتو نهائي)",
        snr_warning_ar=None,
        final_decision="BUY",
    )
    assert rr is None
    assert rr_ar is None
    assert warning == SNR_INSIDE_ZONE_WARNING_AR


def test_normalize_strips_hard_block_ar_even_without_code() -> None:
    rr, rr_ar, warning = normalize_snr_consensus_fields(
        rejection_reason=None,
        rejection_reason_ar="انتظار — SNR Zone Block (فيتو نهائي)",
        snr_warning_ar=None,
        final_decision="SELL",
    )
    assert rr is None
    assert rr_ar is None
    assert warning == SNR_INSIDE_ZONE_WARNING_AR


def test_is_snr_hard_block_message() -> None:
    assert is_snr_hard_block_message("انتظار — SNR Zone Block (فيتو نهائي)") is True
    assert is_snr_hard_block_message(SNR_INSIDE_ZONE_WARNING_AR) is False
