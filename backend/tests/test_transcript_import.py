from qunxue_api.adapters.transcription.importer import parse_imported_transcript


def test_imports_srt_with_chinese_speaker_and_original_timecodes() -> None:
    parsed = parse_imported_transcript(
        filename="访谈.srt",
        media_type="application/x-subrip",
        content=(
            "1\n00:00:01,250 --> 00:00:03,800\n主持人：请先介绍一下自己。\n\n"
            "2\n00:00:04,100 --> 00:00:06,900\n受访者：我在这里住了十年。\n"
        ).encode(),
    )

    assert [(item.start_ms, item.end_ms, item.speaker, item.text) for item in parsed.segments] == [
        (1_250, 3_800, "主持人", "请先介绍一下自己。"),
        (4_100, 6_900, "受访者", "我在这里住了十年。"),
    ]


def test_imports_webvtt_voice_spans_without_losing_chinese_text() -> None:
    parsed = parse_imported_transcript(
        filename="焦点小组.vtt",
        media_type="text/vtt",
        content=(
            "WEBVTT\n\n"
            "00:00:00.000 --> 00:00:02.500\n<v 参与者 A>这个变化很突然。\n\n"
            "00:00:02.500 --> 00:00:05.000\n<v 参与者 B>但后来大家适应了。\n"
        ).encode(),
    )

    assert parsed.source_format == "vtt"
    assert [item.speaker for item in parsed.segments] == ["参与者 A", "参与者 B"]
    assert [item.text for item in parsed.segments] == ["这个变化很突然。", "但后来大家适应了。"]


def test_plain_text_import_keeps_untimed_segments_for_manual_alignment() -> None:
    parsed = parse_imported_transcript(
        filename="访谈.txt",
        media_type="text/plain",
        content="主持人：先从哪里说起？\n\n受访者：从搬家那年说起。".encode(),
    )

    assert [(item.start_ms, item.end_ms, item.speaker) for item in parsed.segments] == [
        (None, None, "主持人"),
        (None, None, "受访者"),
    ]
