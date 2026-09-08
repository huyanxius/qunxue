from io import BytesIO
from zipfile import ZipFile

import pytest

from qunxue_api.adapters.research_materials import parse_material
from qunxue_api.modules.research_materials import MaterialParseError


def pptx_fixture():
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(
            "ppt/presentation.xml",
            """<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<p:sldIdLst>
<p:sldId id="256" r:id="rId2"/>
<p:sldId id="257" r:id="rId1"/>
</p:sldIdLst>
</p:presentation>""",
        )
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId2" Target="slides/slide2.xml"/>
<Relationship Id="rId1" Target="slides/slide1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "ppt/slides/slide2.xml",
            """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld>
<p:spTree>
<p:sp>
<p:nvSpPr>
<p:cNvPr id="1" name="title"/>
<p:nvPr>
<p:ph type="title"/>
</p:nvPr>
</p:nvSpPr>
<p:txBody>
<a:p>
<a:r>
<a:t>访谈方法</a:t>
</a:r>
</a:p>
</p:txBody>
</p:sp>
<p:sp>
<p:txBody>
<a:p>
<a:r>
<a:t>课堂标记 QX-A17</a:t>
</a:r>
</a:p>
</p:txBody>
</p:sp>
<p:sp>
<p:nvSpPr>
<p:cNvPr id="3" hidden="1"/>
</p:nvSpPr>
<p:txBody>
<a:p>
<a:r>
<a:t>隐藏参考答案</a:t>
</a:r>
</a:p>
</p:txBody>
</p:sp>
</p:spTree>
</p:cSld>
</p:sld>""",
        )
        archive.writestr(
            "ppt/slides/slide1.xml",
            """<p:sld show="0" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld>
<p:spTree>
<p:sp>
<p:txBody>
<a:p>
<a:r>
<a:t>隐藏整页</a:t>
</a:r>
</a:p>
</p:txBody>
</p:sp>
</p:spTree>
</p:cSld>
</p:sld>""",
        )
        archive.writestr("ppt/notesSlides/notesSlide2.xml", "教师私人备注，不得分享")
    return data.getvalue()


def test_pptx_uses_presentation_order_and_excludes_notes_and_hidden_content():
    result = parse_material(filename="课堂.pptx", media_type=None, content=pptx_fixture())
    assert "QX-A17" in result.full_text
    assert "隐藏" not in result.full_text
    assert "私人备注" not in result.full_text
    assert result.blocks[0].locator.page == 1


def test_invalid_pptx_is_not_reported_ready():
    with pytest.raises(MaterialParseError):
        parse_material(filename="课堂.pptx", media_type=None, content=b"broken file")


def test_pptx_excludes_hidden_groups_and_tables():
    original = BytesIO(pptx_fixture())
    output = BytesIO()
    with ZipFile(original) as source, ZipFile(output, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name == "ppt/slides/slide2.xml":
                hidden = """<p:grpSp><p:nvGrpSpPr><p:cNvPr hidden="1"/></p:nvGrpSpPr>
<p:sp><p:txBody><a:p><a:r><a:t>分组私人答案</a:t></a:r></a:p></p:txBody></p:sp></p:grpSp>
<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr hidden="1"/></p:nvGraphicFramePr>
<a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>表格私人答案</a:t>
</a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>"""
                content = content.replace(b"</p:spTree>", hidden.encode() + b"</p:spTree>")
            target.writestr(name, content)
    result = parse_material(filename="课堂.pptx", media_type=None, content=output.getvalue())
    assert "私人答案" not in result.full_text
