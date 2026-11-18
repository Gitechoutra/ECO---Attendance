"""Company-branded PDF documents (ReportLab): offer letters, payslips and tabular reports."""
import io
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

LOGO = Path(__file__).resolve().parents[1] / "assets" / "echoutra-logo.png"
NIGHT = colors.HexColor("#050B0F")
TEAL = colors.HexColor("#00BEA3")
DEEP = colors.HexColor("#06766C")
INK = colors.HexColor("#0B141A")
MUTED = colors.HexColor("#62707A")
LINE = colors.HexColor("#E6EAED")
SOFT = colors.HexColor("#F5F7F8")

_ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=_ss["Normal"], fontName="Helvetica", fontSize=10, leading=15, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=11, textColor=MUTED)
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=INK, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=DEEP,
                    spaceBefore=10, spaceAfter=6)
RIGHT = ParagraphStyle("right", parent=BODY, alignment=TA_RIGHT)


def _header_footer(company: dict, title: str):
    def draw(canvas, doc):
        w, h = doc.pagesize
        canvas.saveState()
        canvas.setFillColor(NIGHT)
        canvas.rect(0, h - 26 * mm, w, 26 * mm, stroke=0, fill=1)
        if LOGO.exists():
            lh = 13 * mm
            canvas.drawImage(str(LOGO), 15 * mm, h - 19.5 * mm, width=lh * 1118 / 303, height=lh, mask="auto")
        canvas.setFillColor(colors.HexColor("#A9BAC4"))
        canvas.setFont("Helvetica", 8)
        y = h - 11 * mm
        for line in [company.get("email") or "", company.get("phone") or "", company.get("website") or ""]:
            if line:
                canvas.drawRightString(w - 15 * mm, y, line)
                y -= 3.6 * mm
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(1.2)
        canvas.line(0, h - 26 * mm, w, h - 26 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.5)
        addr = (company.get("address") or "").replace("\n", ", ")
        canvas.drawString(15 * mm, 10 * mm, f"{company.get('legal_name') or company.get('company_name')}"
                                            + (f"  ·  {addr}" if addr else ""))
        canvas.drawRightString(w - 15 * mm, 10 * mm, f"{title}  ·  Page {doc.page}")
        canvas.restoreState()
    return draw


def _doc(buf, pagesize=A4):
    return SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=18 * mm, rightMargin=18 * mm,
                             topMargin=34 * mm, bottomMargin=20 * mm)


def _p(text: str, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def money(v, currency="INR") -> str:
    sym = "Rs. " if currency == "INR" else f"{currency} "
    return f"{sym}{float(v or 0):,.2f}"


def _grid(rows, widths, header=True, zebra=True, align_right_cols=()):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
                  ("TEXTCOLOR", (0, 0), (-1, 0), MUTED)]
    for c in align_right_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def render_template(body: str, ctx: dict) -> str:
    out = body
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v if v is not None else ""))
    return out


def offer_letter_pdf(company: dict, offer: dict, body_text: str) -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf)
    story = [
        Table([[_p(f"Ref: {offer['reference_no']}", SMALL), _p(f"Date: {offer['issue_date']:%d %B %Y}", RIGHT)]],
              colWidths=[87 * mm, 87 * mm], style=[("LEFTPADDING", (0, 0), (-1, -1), 0)]),
        Spacer(1, 8),
        _p(offer["recipient_name"], ParagraphStyle("to", parent=BODY, fontName="Helvetica-Bold")),
        _p(offer["recipient_email"], SMALL),
        Spacer(1, 12),
        _p("Offer of Employment", H1),
        Spacer(1, 6),
    ]
    for para in body_text.split("\n\n"):
        story += [_p(para.strip()), Spacer(1, 7)]
    if offer.get("salary_breakup"):
        rows = [["Component", "Monthly", "Annual"]]
        for r in offer["salary_breakup"]:
            rows.append([r["label"], money(r.get("monthly")), money(r.get("annual"))])
        rows.append(["Total Cost to Company", money(float(offer["annual_ctc"]) / 12), money(offer["annual_ctc"])])
        t = _grid(rows, [90 * mm, 42 * mm, 42 * mm], align_right_cols=(1, 2))
        t.setStyle(TableStyle([("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9), ("BACKGROUND", (0, -1), (-1, -1), SOFT)]))
        story += [KeepTogether([_p("Annexure A — Compensation Structure", H2), t])]
    story += [Spacer(1, 24), Table([[
        _p("For " + company.get("company_name", ""), BODY), _p("Accepted by", RIGHT)], [
        _p("<br/><br/>Authorised Signatory", SMALL), _p(f"<br/><br/>{escape(offer['recipient_name'])}", RIGHT)]],
        colWidths=[87 * mm, 87 * mm], style=[("LEFTPADDING", (0, 0), (-1, -1), 0)])]
    if offer.get("acceptance"):
        story += [Spacer(1, 10), _p(offer["acceptance"], SMALL)]
    doc.build(story, onFirstPage=_header_footer(company, "Offer Letter"),
              onLaterPages=_header_footer(company, "Offer Letter"))
    return buf.getvalue()


def payslip_pdf(company: dict, slip: dict) -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf)
    e = slip["employee"]
    period = slip["period"]
    info = [
        ["Employee", e["full_name"], "Employee ID", e["employee_code"]],
        ["Designation", e.get("designation") or "—", "Department", e.get("department") or "—"],
        ["Working days", f"{slip['working_days']:g}", "Paid days", f"{slip['paid_days']:g}"],
        ["Loss of pay days", f"{slip['lop_days']:g}", "Bank A/C", e.get("bank_account") or "—"],
    ]
    it = Table(info, colWidths=[32 * mm, 55 * mm, 32 * mm, 55 * mm])
    it.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
                            ("TEXTCOLOR", (2, 0), (2, -1), MUTED), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    earn, ded = slip["breakdown"]["earnings"], slip["breakdown"]["deductions"]
    n = max(len(earn), len(ded))
    rows = [["Earnings", "Amount", "Deductions", "Amount"]]
    for i in range(n):
        a = earn[i] if i < len(earn) else None
        b = ded[i] if i < len(ded) else None
        rows.append([a["name"] if a else "", money(a["amount"]) if a else "", b["name"] if b else "",
                     money(b["amount"]) if b else ""])
    rows.append(["Gross earnings", money(slip["gross_earnings"]), "Total deductions", money(slip["total_deductions"])])
    t = _grid(rows, [52 * mm, 35 * mm, 52 * mm, 35 * mm], align_right_cols=(1, 3))
    t.setStyle(TableStyle([("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 9), ("BACKGROUND", (0, -1), (-1, -1), SOFT)]))
    net = Table([[_p("<b>Net pay</b>"), _p(f"<b>{money(slip['net_pay'])}</b>", RIGHT)]], colWidths=[87 * mm, 87 * mm])
    net.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E0F7F2")),
                             ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10)]))
    story = [_p(f"Payslip for {period}", H1), _p(company.get("company_name", ""), SMALL), Spacer(1, 12), it,
             Spacer(1, 12), t, Spacer(1, 10), net, Spacer(1, 18),
             _p("This is a system-generated payslip and does not require a signature.", SMALL)]
    doc.build(story, onFirstPage=_header_footer(company, f"Payslip {period}"),
              onLaterPages=_header_footer(company, f"Payslip {period}"))
    return buf.getvalue()


def table_report_pdf(company: dict, title: str, subtitle: str, columns: list[str], rows: list[list],
                     summary: list[tuple[str, str]] | None = None) -> bytes:
    buf = io.BytesIO()
    wide = len(columns) > 6
    pagesize = landscape(A4) if wide else A4
    doc = _doc(buf, pagesize)
    usable = pagesize[0] - 36 * mm
    story = [_p(title, H1), _p(subtitle, SMALL), Spacer(1, 10)]
    if summary:
        cells = [[_p(f"<font size=8 color='#62707A'>{escape(k)}</font><br/><b>{escape(str(v))}</b>") for k, v in summary]]
        st = Table(cells, colWidths=[usable / len(summary)] * len(summary))
        st.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                                ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story += [st, Spacer(1, 12)]
    data = [columns] + [[_p(c, ParagraphStyle("c", parent=BODY, fontSize=8.5, leading=11)) for c in r] for r in rows]
    if not rows:
        data.append([_p("No records for the selected filters.", SMALL)] + [""] * (len(columns) - 1))
    story.append(_grid(data, [usable / len(columns)] * len(columns)))
    story += [Spacer(1, 10), _p(f"Generated on {date.today():%d %b %Y} · Confidential", SMALL)]
    doc.build(story, onFirstPage=_header_footer(company, title), onLaterPages=_header_footer(company, title))
    return buf.getvalue()
