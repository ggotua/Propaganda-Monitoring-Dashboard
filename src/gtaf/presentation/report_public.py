"""Bilingual (EN/KA) public report renderer (SPEC-018).

Self-contained: no external stylesheet, font or script, because the file is meant to be published on GitHub Pages
and opened from an email. The language toggle is a few lines of inline JavaScript that swaps the text of every
element carrying both `data-en` and `data-ka`.
"""

from __future__ import annotations

import html

from gtaf.application.report_public import PublicReport

STYLE = """
:root { color-scheme: light; }
body { margin: 0; background: #fbfaf7; color: #1b1b19; font-family: Georgia, 'Times New Roman', serif; }
main { max-width: 900px; margin: 0 auto; padding: 56px 28px 96px; }
header { border-bottom: 2px solid #1b1b19; padding-bottom: 18px; margin-bottom: 30px; }
h1 { font-size: 34px; line-height: 1.15; margin: 0 0 10px; letter-spacing: -0.015em; }
h2 { font-size: 21px; margin: 44px 0 12px; }
p, li, td, th { font-size: 16px; line-height: 1.6; }
.lede { font-size: 19px; color: #33322f; }
.finding { display: flex; flex-wrap: wrap; gap: 18px; margin: 26px 0 8px; }
.card { flex: 1 1 220px; border: 1px solid #ddd8cd; background: #fff; padding: 16px 18px; }
.card .big { font-size: 40px; line-height: 1; margin-bottom: 8px; }
.card .label { font-size: 14px; color: #6b675f; }
.banner { background: #fff3d6; border-left: 4px solid #c98a00; padding: 14px 18px; margin: 24px 0; font-size: 15px; }
table { border-collapse: collapse; width: 100%; margin: 14px 0; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e6e2d8; }
th { background: #f0ece2; font-weight: 600; font-size: 14px; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.gov { background: #e3ecf7; } .opp { background: #f9e3e3; } .ind { background: #ececec; }
.tag { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 13px; }
.toggle { position: sticky; top: 0; background: #fbfaf7; padding: 10px 0; text-align: right; }
.toggle button { font: inherit; padding: 4px 12px; border: 1px solid #1b1b19; background: #fff; cursor: pointer; }
.toggle button[aria-pressed="true"] { background: #1b1b19; color: #fff; }
footer { margin-top: 56px; border-top: 1px solid #ddd8cd; padding-top: 16px; font-size: 13px; color: #6b675f; }
code { font-size: 13px; }
.note { font-size: 14px; color: #6b675f; }
"""

SCRIPT = """
function setLang(lang) {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-en]').forEach(function (node) {
    var value = node.getAttribute('data-' + lang);
    if (value !== null) { node.textContent = value; }
  });
  document.querySelectorAll('[data-en-html]').forEach(function (node) {
    var value = node.getAttribute('data-' + lang + '-html');
    if (value !== null) { node.innerHTML = value; }
  });
  document.querySelectorAll('.toggle button').forEach(function (button) {
    button.setAttribute('aria-pressed', String(button.dataset.lang === lang));
  });
}
document.querySelectorAll('.toggle button').forEach(function (button) {
  button.addEventListener('click', function () { setLang(button.dataset.lang); });
});
"""


def _t(english: str, georgian: str) -> str:
    """Return a bilingual inline element.

    Args:
        english: English text.
        georgian: Georgian text.

    Returns:
        A span carrying both languages, so the toggle can swap it without reloading.
    """
    return (
        f'<span data-en="{html.escape(english, quote=True)}" '
        f'data-ka="{html.escape(georgian, quote=True)}">{html.escape(english)}</span>'
    )


def _leaning_tag(leaning: str, assigned: bool) -> str:
    """Return a leaning badge, marking an unassigned leaning honestly.

    Args:
        leaning: Stored leaning value.
        assigned: Whether the value is an editorial judgement.

    Returns:
        HTML for the badge.
    """
    if not assigned:
        return f'<span class="tag ind">{_t("unassigned", "მიუკუთვნებელი")}</span>'
    css = {"pro-government": "gov", "opposition": "opp"}.get(leaning, "ind")
    label_en = {"pro-government": "pro-government", "opposition": "opposition"}.get(leaning, leaning)
    label_ka = {"pro-government": "მთავრობის მხარდამჭერი", "opposition": "ოპოზიციური"}.get(leaning, leaning)
    return f'<span class="tag {css}">{_t(label_en, label_ka)}</span>'


def _pct(value: float) -> str:
    """Format a share as a percentage."""
    return f"{value * 100:.1f}%"


def render_public_report(report: PublicReport) -> str:
    """Render the bilingual public report.

    Args:
        report: Assembled data.

    Returns:
        A complete, self-contained HTML document.
    """
    government = next(
        (row for row in report.groups if row.group == "government" and row.leaning == "pro-government"),
        None,
    )
    opposition = next(
        (row for row in report.groups if row.group == "government" and row.leaning == "opposition"),
        None,
    )
    reverse = next(
        (row for row in report.groups if row.group == "opposition" and row.leaning == "pro-government"),
        None,
    )
    sum(1 for _id, _leaning, is_assigned, _t, _d, _f, _l in report.sources if is_assigned)
    total_labels = report.labels

    parts: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Who gets criticised — Georgian political coverage on two channel websites</title>",
        f"<style>{STYLE}</style></head><body><main>",
        "<div class='toggle'>"
        "<button type='button' data-lang='en' aria-pressed='true'>English</button> "
        "<button type='button' data-lang='ka' aria-pressed='false'>ქართული</button>"
        "</div>",
        "<header>",
        f"<h1>{_t('Who gets criticised', 'ვინ იკრიტიკება')}</h1>",
        "<p class='lede'>"
        + _t(
            "Georgian political coverage on the websites of Imedi (pro-government) and TV Pirveli "
            "(opposition), November 2026. Each source's actual window and date coverage is listed in section 4.",
            "ქართული პოლიტიკური გაშუქება იმედის (მთავრობის მხარდამჭერი) და ტვ პირველის "
            "(ოპოზიციური) ვებგვერდებზე, 2026 წლის ნოემბერი. თითოეული წყაროს ფაქტობრივი პერიოდი და "
            "დათარიღების სისრულე მოცემულია მე-4 ნაწილში.",
        )
        + "</p>",
        "</header>",
    ]

    parts.append(
        "<div class='finding'>"
        f"<div class='card'><div class='big'>{government.critical if government else 0}</div>"
        f"<div class='label'>{_t('critical items about government figures on Imedi', 'კრიტიკული მასალა მთავრობის ფიგურებზე იმედზე')}"
        f" {('of ' + str(government.publications)) if government else ''}</div></div>"
        f"<div class='card'><div class='big'>{opposition.critical if opposition else 0}</div>"
        f"<div class='label'>{_t('critical items about the same figures on TV Pirveli', 'კრიტიკული მასალა იმავე ფიგურებზე ტვ პირველზე')}"
        f" {('of ' + str(opposition.publications)) if opposition else ''}</div></div>"
        f"<div class='card'><div class='big'>{reverse.critical if reverse else 0}</div>"
        f"<div class='label'>{_t('critical items about Saakashvili and Zourabichvili on Imedi', 'კრიტიკული მასალა სააკაშვილსა და ზურაბიშვილზე იმედზე')}"
        f" {('of ' + str(reverse.publications)) if reverse else ''}</div></div>"
        "</div>"
    )

    parts.append(
        "<div class='banner'>"
        + _t(
            "These figures describe websites, not airtime. A separate check of Imedi's site against its "
            "television output measured 0.673 rank correlation, below the 0.7 threshold this project set, so "
            "the website may not be used as a proxy for what was broadcast.",
            "ეს მაჩვენებლები ეხება ვებგვერდებს და არა ეთერს. იმედის საიტის ეთერთან შედარებამ აჩვენა 0.673 "
            "რანგული კორელაცია — პროექტის 0.7 ზღვარზე დაბლა, ამიტომ საიტი ვერ გამოდგება ეთერის შემცვლელად.",
        )
        + "</div>"
    )

    parts.append(f"<h2>{_t('1. The numbers', '1. ციფრები')}</h2>")
    parts.append(
        "<table><tr><th>"
        + _t("Figures", "ფიგურები")
        + "</th><th>"
        + _t("Outlet", "მედია")
        + "</th><th class='num'>"
        + _t("publications", "პუბლიკაცია")
        + "</th><th class='num'>"
        + _t("critical", "კრიტიკული")
        + "</th><th class='num'>"
        + _t("supportive", "მხარდამჭერი")
        + "</th></tr>"
    )
    for row in report.groups:
        group_label = (
            _t("government (7 figures)", "მთავრობა (7 ფიგურა)")
            if row.group == "government"
            else _t("opposition (2 figures)", "ოპოზიცია (2 ფიგურა)")
        )
        parts.append(
            f"<tr><td>{group_label}</td><td>{_leaning_tag(row.leaning, True)}</td>"
            f"<td class='num'>{row.publications}</td><td class='num'>{row.critical} "
            f"({_pct(row.critical_rate)})</td><td class='num'>{row.supportive}</td></tr>"
        )
    parts.append("</table>")
    parts.append(
        "<p class='note'>"
        + _t(
            "Government figures: Kobakhidze, Ivanishvili, Garibashvili, Mdinaradze, Papuashvili, "
            "Kavelashvili, Bochorishvili. Opposition figures: Saakashvili, Zourabichvili.",
            "მთავრობის ფიგურები: კობახიძე, ივანიშვილი, ღარიბაშვილი, მდინარაძე, პაპუაშვილი, "
            "ყაველაშვილი, ბოჭორიშვილი. ოპოზიციის ფიგურები: სააკაშვილი, ზურაბიშვილი.",
        )
        + "</p>"
    )

    parts.append(f"<h2>{_t('2. How it was measured', '2. როგორ გავზომეთ')}</h2>")
    parts.append(
        "<ul>"
        f"<li>{_t('Collection', 'შეგროვება')}: "
        + _t(
            f"{report.publications} publications from {len(report.sources)} outlets, article text extracted "
            "and reduced to a stored excerpt; related-article teasers, navigation and markup are removed.",
            f"{report.publications} პუბლიკაცია {len(report.sources)} მედიიდან; ტექსტი იწმინდება "
            "სარეკლამო ბლოკების, ნავიგაციისა და მარკირებისგან.",
        )
        + "</li>"
        f"<li>{_t('Name matching', 'სახელების დამთხვევა')}: "
        + _t(
            "a surname dictionary with Georgian case endings. A bare surname is not enough for shared names: "
            "Bidzina Ivanishvili needs his first name or a known alias, and Zurabashvili is never matched to "
            "Zourabichvili.",
            "გვარების ლექსიკონი ქართული ბრუნვის ნიშნებით. საერთო გვარებისთვის მხოლოდ გვარი საკმარისი არ არის: "
            "ბიძინა ივანიშვილს სჭირდება სახელი ან ცნობილი მეტსახელი, ზურაბაშვილი კი არასდროს "
            "ემთხვევა ზურაბიშვილს.",
        )
        + "</li>"
        f"<li>{_t('Stance', 'დამოკიდებულება')}: "
        + _t(
            f"{total_labels} labels from a language model (prompt stance-v5) with four categories — "
            "supportive, critical, neutral, unclear — each carrying a verbatim quote from the text.",
            f"{total_labels} ნიშანი ენის მოდელისგან (პრომპტი stance-v5) ოთხ კატეგორიად: "
            "მხარდამჭერი, კრიტიკული, ნეიტრალური, გაურკვეველი — თითოეულს აქვს ზუსტი ციტატა.",
        )
        + "</li>"
        f"<li>{_t('Human check', 'ადამიანური შემოწმება')}: "
        + _t(
            "four rounds of hand labelling by a reviewer who did not see the model's answer first: 37/40, "
            "27/30, 28/30 exact, and 20/20 on a random draw from the full corpus. Critical recall 4 of 5.",
            "ოთხი რაუნდი ხელით მარკირებისა: 37/40, 27/30, 28/30 ზუსტი და 20/20 სრული კორპუსიდან "
            "შემთხვევით აღებულ ნიმუშზე. კრიტიკის ამოცნობა 4/5.",
        )
        + "</li>"
        "</ul>"
    )

    parts.append(f"<h2>{_t('3. What this cannot support', '3. რას არ ამტკიცებს')}</h2>")
    parts.append(
        "<ul>"
        f"<li>{_t('Not airtime.', 'ეს არ არის ეთერი.')} "
        + _t(
            "Website publications are a different corpus from broadcast transcripts and are never merged with it.",
            "ვებპუბლიკაციები ცალკე კორპუსია და არასდროს ერწყმის ეთერს.",
        )
        + "</li>"
        f"<li>{_t('Supportive is thin.', 'მხარდამჭერი ცოტაა.')} "
        + _t(
            "Six rows in the whole corpus. It is reported as a count, never as a rate.",
            "მთელ კორპუსში ექვსი ჩანაწერია. მოცემულია როგორც რაოდენობა და არა პროცენტი.",
        )
        + "</li>"
        f"<li>{_t('Two outlets carry the finding.', 'დასკვნას ორი მედია ატარებს.')} "
        + _t(
            "The comparison rests on Imedi and TV Pirveli, which hold "
            f"{sum(count for _source, count in report.labels_by_source[:2])} of the {report.labels} stance rows. "
            "The other outlets contribute a handful between them, and Rustavi 2 has no editorial leaning "
            "recorded at all — it is marked unassigned and excluded from every leaning comparison.",
            "შედარება ეყრდნობა იმედსა და ტვ პირველს — მათზე მოდის "
            f"{sum(count for _source, count in report.labels_by_source[:2])} ნიშანი {report.labels}-დან. "
            "დანარჩენი მედია ერთად რამდენიმე ჩანაწერს იძლევა, ხოლო Rustavi 2-ს რედაქციული ორიენტაცია "
            "საერთოდ არ აქვს ჩაწერილი და ყოველი შედარებიდან გამორიცხულია.",
        )
        + "</li>"
        f"<li>{_t('This is a classifier, not a reader.', 'ეს კლასიფიკატორია და არა მკითხველი.')} "
        + _t(
            "Stance labels come from a model. The direction is well supported by the human checks; a single "
            "percentage point is not.",
            "ნიშნები მოდელისგანაა. მიმართულება ადამიანური შემოწმებით დადასტურებულია, ცალკეული პროცენტი — არა.",
        )
        + "</li>"
        "</ul>"
    )

    parts.append(f"<h2>{_t('4. Sources', '4. წყაროები')}</h2>")
    parts.append(
        "<table><tr><th>"
        + _t("Outlet", "მედია")
        + "</th><th>"
        + _t("Leaning", "ორიენტაცია")
        + "</th><th class='num'>"
        + _t("publications", "პუბლიკაცია")
        + "</th><th>"
        + _t("window", "პერიოდი")
        + "</th></tr>"
    )
    for source_id, leaning, is_assigned, total, dated, first, last in report.sources:
        # A window computed from partial dates would claim the outlet published for two days when most of its
        # items simply carry no timestamp. Show the coverage instead of the misleading range.
        if first and last and dated:
            window = f"{first} to {last} · {dated}/{total} dated"
        else:
            window = _t(f"no dates · {dated}/{total} dated", f"უთარიღო · {dated}/{total} დათარიღებული")
        parts.append(
            f"<tr><td>{html.escape(source_id)}</td><td>{_leaning_tag(leaning, is_assigned)}</td>"
            f"<td class='num'>{total}</td><td>{window}</td></tr>"
        )
    parts.append("</table>")
    parts.append(
        "<p class='note'>"
        + _t(
            "Dates come from the outlet's listing where one exposes a publication time, and from the sitemap's "
            "last-modified field otherwise. A sitemap date records the last edit, not necessarily the "
            "publication, which is why a source can show a two-day window while its archive is older.",
            "თარიღები აღებულია გამოცემის სიიდან, სადაც გამოქვეყნების დრო ჩანს, ხოლო სხვა შემთხვევაში — "
            "საიტის რუკის ბოლო ცვლილების ველიდან. რუკის თარიღი ნიშნავს ბოლო რედაქტირებას და არა "
            "აუცილებლად გამოქვეყნებას — ამიტომ წყაროს ორდღიანი ფანჯარა შეიძლება ჰქონდეს, მიუხედავად "
            "უფრო ძველი არქივისა.",
        )
        + "</p>"
    )
    parts.append(
        "<p class='note'>"
        + _t(
            "Leaning labels are editorial judgements stored as data, attributable and revisable — never produced "
            "by a model. Article body text is not stored or redistributed; excerpts and hashes only.",
            "ორიენტაციის ნიშნები რედაქციული შეფასებებია, მონაცემად შენახული — არასდროს მოდელის მიერ "
            "გენერირებული. სტატიების სრული ტექსტი არ ინახება და არ ვრცელდება; მხოლოდ ამონაკვეთები.",
        )
        + "</p>"
    )

    versions = ", ".join(f"{html.escape(name)} {html.escape(value)}" for name, value in report.versions)
    parts.append(
        f"<footer>{_t('Generated', 'გენერირებულია')} {report.generated_on.isoformat()} · "
        f"{_t('provenance', 'წარმომავლობა')}: {versions}<br>"
        + _t(
            "Built by GTAF, a monitoring pipeline for Georgian political media. Method and decisions are "
            "documented in the repository.",
            "შექმნილია GTAF-ის მიერ — ქართული პოლიტიკური მედიის მონიტორინგის პაიპლაინი. მეთოდი და "
            "გადაწყვეტილებები დოკუმენტირებულია რეპოზიტორიაში.",
        )
        + "</footer>"
    )
    parts.append(f"</main><script>{SCRIPT}</script></body></html>")
    return "\n".join(parts)
