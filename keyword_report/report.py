"""HTML template + WeasyPrint PDF generation matching IdealReport.jpeg design."""

from pathlib import Path

from weasyprint import HTML


def _pluralize_industry(industry: str) -> str:
    """Convert industry to customer-friendly plural form."""
    plurals = {
        "plumbing": "plumbers",
        "hvac": "HVAC companies",
        "roofing": "roofers",
        "electrical": "electricians",
        "painting": "painters",
        "landscaping": "landscapers",
        "cleaning": "cleaning services",
        "pest_control": "pest control companies",
    }
    return plurals.get(industry.lower().replace(" ", "_"), f"{industry} businesses")


def _format_number(n: int) -> str:
    """Format number with commas: 1420 -> '1,420'."""
    return f"{n:,}"


def generate_report_pdf(
    business_name: str,
    industry: str,
    keywords: list[dict],
    output_path: Path,
) -> Path:
    """
    Generate a keyword opportunity PDF report.

    Args:
        business_name: Extracted business name
        industry: Business industry
        keywords: List of {"keyword": str, "monthly_searches": int, "on_old_site": bool}
        output_path: Where to save the PDF

    Returns:
        Path to the generated PDF
    """
    industry_plural = _pluralize_industry(industry)
    total_impressions = sum(kw["monthly_searches"] for kw in keywords)
    old_site_count = sum(1 for kw in keywords if kw["on_old_site"])
    new_site_count = len(keywords)

    # Build keyword rows HTML
    keyword_rows = ""
    for kw in keywords:
        impressions = _format_number(kw["monthly_searches"])

        if kw["on_old_site"]:
            old_site_icon = (
                '<span class="check-circle check-yes">'
                '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
                '<circle cx="8" cy="8" r="8" fill="#4ecdc4"/>'
                '<path d="M5 8l2 2 4-4" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
                '</svg>'
                '</span>'
            )
        else:
            old_site_icon = (
                '<span class="check-circle check-no">'
                '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
                '<circle cx="8" cy="8" r="8" fill="#c5c9d1"/>'
                '<path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="#4a4a5a" stroke-width="1.6" stroke-linecap="round"/>'
                '</svg>'
                '</span>'
            )

        new_site_icon = (
            '<span class="check-circle check-yes">'
            '<svg width="16" height="16" viewBox="0 0 16 16" fill="none">'
            '<circle cx="8" cy="8" r="8" fill="#4ecdc4"/>'
            '<path d="M5 8l2 2 4-4" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
            '</svg>'
            '</span>'
        )

        keyword_rows += f"""
        <tr class="keyword-row">
            <td class="kw-name">{kw["keyword"]}</td>
            <td class="kw-impressions"><span class="pill">{impressions}/mo</span></td>
            <td class="kw-check">{old_site_icon}</td>
            <td class="kw-check">{new_site_icon}</td>
        </tr>
        """

    # Total row old site display
    if old_site_count > 0:
        old_total_display = f'<span class="total-number">{old_site_count}</span>'
    else:
        old_total_display = f'<span class="total-number">{old_site_count}</span>'

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 30px;
    }}

    * {{
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }}

    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        background: #f0f2f5;
        color: #1a1a2e;
        -webkit-font-smoothing: antialiased;
    }}

    .container {{
        max-width: 780px;
        margin: 0 auto;
        padding: 0;
    }}

    /* Top teal gradient bar */
    .top-bar {{
        height: 5px;
        background: linear-gradient(90deg, #4ecdc4, #3dbdb5);
        border-radius: 3px 3px 0 0;
    }}

    /* Header section */
    .header {{
        padding: 40px 40px 0 40px;
    }}

    .prepared-for {{
        font-size: 12px;
        font-weight: 700;
        color: #1a1a2e;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin-bottom: 4px;
    }}

    .business-name {{
        font-size: 32px;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 4px;
    }}

    .report-subtitle {{
        font-size: 15px;
        font-weight: 400;
        color: #9ca3af;
        margin-bottom: 32px;
    }}

    /* Intro block with teal left border */
    .intro-block {{
        border-left: 4px solid #4ecdc4;
        padding: 20px 24px;
        margin: 0 40px 40px 40px;
        background: white;
    }}

    .intro-block p {{
        font-size: 15px;
        line-height: 1.7;
        color: #374151;
        margin-bottom: 12px;
    }}

    .intro-block p:last-child {{
        margin-bottom: 0;
    }}

    /* Keywords section */
    .keywords-section {{
        padding: 0 40px;
    }}

    .card-heading {{
        font-size: 22px;
        font-weight: 700;
        color: #1a1a2e;
        margin-bottom: 6px;
    }}

    .card-subtitle {{
        font-size: 14px;
        font-weight: 400;
        color: #6b7280;
        margin-bottom: 28px;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
    }}

    thead th {{
        text-transform: uppercase;
        font-size: 11px;
        font-weight: 600;
        color: #8b95a5;
        letter-spacing: 0.05em;
        padding: 0 12px 12px 12px;
        border-bottom: 1px solid #e8eaed;
    }}

    th.col-keyword {{
        text-align: left;
        width: 42%;
    }}

    th.col-impressions {{
        text-align: center;
        width: 26%;
    }}

    th.col-check {{
        text-align: center;
        width: 16%;
    }}

    .keyword-row td {{
        padding: 14px 12px;
        border-bottom: 1px solid #e8eaed;
        vertical-align: middle;
    }}

    .kw-name {{
        font-size: 15px;
        font-weight: 400;
        color: #1a1a2e;
    }}

    .kw-impressions {{
        text-align: center;
    }}

    .pill {{
        display: inline-block;
        background: #1a3a4a;
        color: white;
        font-size: 13px;
        font-weight: 500;
        padding: 4px 14px;
        border-radius: 20px;
        white-space: nowrap;
    }}

    .kw-check {{
        text-align: center;
    }}

    .check-circle {{
        display: inline-block;
        line-height: 0;
    }}

    /* Total row */
    .total-row td {{
        padding: 16px 12px;
        border-top: 2px solid #d1d5db;
        vertical-align: middle;
    }}

    .total-label {{
        font-size: 15px;
        font-weight: 700;
        color: #1a1a2e;
    }}

    .total-impressions {{
        text-align: center;
    }}

    .pill-total {{
        display: inline-block;
        background: #2ab090;
        color: white;
        font-size: 13px;
        font-weight: 600;
        padding: 4px 14px;
        border-radius: 20px;
        white-space: nowrap;
    }}

    .total-check {{
        text-align: center;
    }}

    .total-number {{
        font-size: 15px;
        font-weight: 400;
        color: #8b95a5;
    }}

    .total-new {{
        font-size: 15px;
        font-weight: 700;
        color: #4ecdc4;
    }}

    /* Bottom banner */
    .banner {{
        background: linear-gradient(135deg, #1a1a2e 0%, #2a2a4e 100%);
        border-radius: 12px;
        margin: 30px 40px 0 40px;
        padding: 32px 40px;
        text-align: center;
    }}

    .banner-heading {{
        font-size: 20px;
        font-weight: 700;
        color: white;
        margin-bottom: 12px;
    }}

    .banner-text {{
        font-size: 14px;
        font-weight: 400;
        color: rgba(255,255,255,0.85);
        line-height: 1.6;
        max-width: 580px;
        margin: 0 auto 20px auto;
    }}

    .pricing-pill {{
        display: inline-block;
        border: 2px solid #4ecdc4;
        color: #4ecdc4;
        font-size: 14px;
        font-weight: 700;
        padding: 10px 28px;
        border-radius: 30px;
    }}

    /* Footer */
    .footer {{
        text-align: center;
        margin: 24px 40px 0 40px;
        padding-top: 16px;
        border-top: 1px solid #e8eaed;
        font-size: 12px;
        color: #9ca3af;
    }}
</style>
</head>
<body>
<div class="container">
    <div class="top-bar"></div>

    <div class="header">
        <div class="prepared-for">Prepared For</div>
        <div class="business-name">{business_name}</div>
        <div class="report-subtitle">Local SEO Opportunity Report</div>
    </div>

    <div class="intro-block">
        <p>
            This example report has been created <strong>specifically for your business</strong>.
            It shows the keywords your customers are already searching for &mdash; and whether
            they're finding you.
        </p>
        <p>
            At ZING, we build your new website along with <strong>50 local landing pages</strong>
            so you rank in more places and get more impressions. That means more people in your
            area see your business when they search &mdash; and more of them get in touch.
        </p>
    </div>

    <div class="keywords-section">
        <div class="card-heading">Your Keywords</div>
        <div class="card-subtitle">These are the search terms your customers use to find {industry_plural} in your area</div>

        <table>
            <thead>
                <tr>
                    <th class="col-keyword">Keyword</th>
                    <th class="col-impressions">Monthly Impressions</th>
                    <th class="col-check">Old Site</th>
                    <th class="col-check">New Site</th>
                </tr>
            </thead>
            <tbody>
                {keyword_rows}
                <tr class="total-row">
                    <td class="total-label">Total</td>
                    <td class="total-impressions"><span class="pill-total">{_format_number(total_impressions)}/mo</span></td>
                    <td class="total-check">{old_total_display}</td>
                    <td class="total-check"><span class="total-new">{new_site_count}</span></td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="banner">
        <div class="banner-heading">What this means for {business_name}</div>
        <div class="banner-text">
            With your new website and 50 landing pages, your business has the potential to appear
            in thousands more local searches every month. More visibility means more enquiries,
            and more enquiries means more jobs.
        </div>
        <span class="pricing-pill">$59/mo &middot; No contract &middot; Cancel anytime</span>
    </div>

    <div class="footer">
        Prepared by ZING Website Design &middot; zing.work
    </div>
</div>
</body>
</html>"""

    # Generate PDF
    output_path = Path(output_path)
    HTML(string=html_content).write_pdf(str(output_path))

    return output_path
