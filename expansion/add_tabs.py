"""Organize the existing portfolio into linked, keyboard-accessible project views."""
from pathlib import Path
import re
import sys


def tabs(identifier, title, links, css=""):
    items = "".join(
        f'<a id="tab-{key}" role="tab" aria-selected="false" aria-controls="{key}" href="#{key}">{name}</a>'
        for key, name in links
    )
    return f'<nav class="tabbar {css}" id="{identifier}" role="tablist" aria-label="{title}">{items}</nav>'


def pane(key, content):
    return f'<div id="{key}" data-pane role="tabpanel" aria-labelledby="tab-{key}">\n{content}\n</div>'


PARATUS = '''<p class="kicker">Career-fit and résumé app</p>
<h2 id="paratus-title">Paratus</h2>
<p>Compare a job posting with a candidate’s career evidence and draft a résumé grounded in what the candidate actually did.</p>
<div class="panel" aria-labelledby="paratus-example-title">
  <h3 id="paratus-example-title">What would you put on the résumé?</h3>
  <p class="note">Fictional, illustrative example. Read the evidence, then see how it shapes the draft.</p>
  <dl class="paratus-example">
    <div><dt>Job posting · IT Program Manager</dt><dd>Lead multi-site IT rollouts and directly manage a team of at least 10.</dd></div>
    <div><dt>Candidate evidence</dt><dd>Coordinated a help-desk platform rollout across six offices, scheduled training for 120 staff, and tracked launch issues. Led a cross-functional project team.</dd></div>
  </dl>
  <details>
    <summary>Reveal the fit assessment and résumé bullet</summary>
    <dl class="paratus-example">
      <div><dt>Supported match</dt><dd>The rollout across six offices supports the multi-site delivery requirement.</dd></div>
      <div><dt>Evidence gap</dt><dd>The profile documents project leadership. Direct management of 10 or more people is unverified.</dd></div>
    </dl>
    <p><strong>Draft résumé bullet</strong></p>
    <blockquote class="guide">Coordinated a help-desk platform rollout across six offices, scheduled training for 120 staff, and tracked launch issues.</blockquote>
    <p class="note">The bullet leaves out a direct-report count because the evidence gives none.</p>
  </details>
</div>
<p><a class="paratus-cta" href="https://role-foundry.onrender.com/">Try the full Paratus app →</a></p>
<p class="note">Choose <strong>Try a fictional sample</strong> in the app to explore with example data.</p>'''

def main(path):
    html = path.read_text()
    projects = [("airport","Flights"),("bike","Citi Bike"),("watts","Watt’s Next"),("paratus","Paratus")]
    html, count = re.subn(r'<nav aria-label="Projects">.*?</nav>', tabs("project-tabs","Projects",projects),html,count=1)
    if count != 1:
        raise ValueError("Project navigation missing.")
    for key, _ in projects:
        marker = f'<section id="{key}" aria-labelledby="{key}-title">'
        if html.count(marker) != 1:
            raise ValueError(marker)
        html = html.replace(marker,f'<section id="{key}" role="tabpanel" aria-labelledby="tab-{key}">',1)

    def organize(key, subsets, prefix):
        nonlocal html
        start = html.index(prefix,html.index(f'<section id="{key}"'))
        end = html.index("</section>",start)
        data = html[start:end]
        chunks = {}
        for chunk, marker in reversed(subsets):
            first = data.index(marker)
            chunks[chunk] = data[first:]
            data = data[:first]
        if data.strip():
            raise ValueError(f"Unexpected ungrouped markup in {key}")
        return start,end,chunks

    flight = [
        ("plan",'<div class="panel" id="flight-decision">'),("replay",'<div class="panel" id="schedule-evaluation">'),
        ("network",'<div class="panel" id="flight-network">'),("ranking",'<div id="planner-performance"'),
        ("compare",'<div class="panel" id="flight-comparison">'),("archive",'<div class="panel" id="flight-holdout">'),
    ]
    start,end,chunks=organize("airport",flight,flight[0][1])
    links=[("flight-planning","Plan a trip"),("flight-explore","Routes and times"),("flight-evidence","Evaluation and sources")]
    html=html[:start]+tabs("flight-tabs","Flight views",links,"subtabs")+pane("flight-planning",chunks["plan"])+pane(
        "flight-explore",chunks["network"]+chunks["compare"])+pane(
        "flight-evidence",chunks["replay"]+chunks["ranking"]+chunks["archive"])+html[end:]

    bike=[
        ("stations",'<div class="panel" id="bike-decision">'),("trend",'<fieldset><legend>Explore the audited archive</legend>'),
        ("weekly",'<div class="panel" id="bike-weekly">'),("evaluation",'<div id="bike-performance"'),
    ]
    start,end,chunks=organize("bike",bike,bike[0][1])
    links=[("bike-review","Station and weekly review"),("bike-trends","Ridership trends"),("bike-evidence","Evaluation and sources")]
    html=html[:start]+tabs("bike-tabs","Citi Bike views",links,"subtabs")+pane("bike-review",chunks["stations"]+chunks["weekly"])+pane(
        "bike-trends",chunks["trend"])+pane("bike-evidence",chunks["evaluation"])+html[end:]

    marker = '<section id="paratus" role="tabpanel" aria-labelledby="tab-paratus">'
    start = html.index(marker) + len(marker)
    end = html.index("</section>", start)
    html = html[:start] + "\n" + PARATUS + "\n" + html[end:]

    marker='<a href="watts-next/">Open Watt’s Next</a></section>'
    if marker in html:
        html=html.replace(marker,'''<p><a href="watts-next/" target="_blank" rel="noopener">Open Watt’s Next in a new tab ↗</a></p>
<iframe class="project-embed" data-src="watts-next/" title="Watt’s Next interactive research dashboard"></iframe></section>''',1)
    html=html.replace('</style>', '''.tabbar{gap:.4rem;align-items:center}
.tabbar [role=tab]{padding:.4rem .7rem;border:1px solid currentColor;border-radius:.4rem;text-decoration:none;line-height:1.4}
.tabbar [role=tab]:hover{text-decoration:underline}
#project-tabs [aria-selected=true]{background:#e3f2ee;color:#14283d;font-weight:700}
.subtabs [aria-selected=true]{background:#edf6f3;color:#134d42;font-weight:700}
.paratus-example{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr));gap:.65rem}.paratus-example div{padding:.65rem .8rem;background:var(--bg);border-radius:.4rem}.paratus-example dt{font-weight:700}.paratus-example dd{margin:.2rem 0 0}.paratus-cta{display:inline-block;background:var(--green);color:white;padding:.45rem .75rem;border-radius:.35rem;font-weight:700;text-decoration:none}.paratus-cta:hover{text-decoration:underline}
.project-embed{width:100%;height:80vh;min-height:28rem;border:1px solid var(--line);border-radius:.5rem}
</style>''',1)
    html=html.replace('</body>','<script src="expansion/project-tabs.js"></script>\n</body>',1)
    path.write_text(html)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
