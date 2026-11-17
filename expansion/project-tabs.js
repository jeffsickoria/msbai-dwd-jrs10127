const projectTablist = document.querySelector('#project-tabs');
const projectTabs = [...projectTablist.querySelectorAll('[role="tab"]')];
const panelsFor = tabs => tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
const projectPanels = panelsFor(projectTabs);
const choose = (tabs, selected) => {
  tabs.forEach((tab, i) => {
    tab.setAttribute('aria-selected', String(i === selected));
    tab.tabIndex = i === selected ? 0 : -1;
  });
  panelsFor(tabs).forEach((panel, i) => { panel.hidden = i !== selected; });
};
const boundTablists = new Set();
function bindTabs(list) {
  if (boundTablists.has(list)) return;
  boundTablists.add(list);
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  list.addEventListener('keydown', event => {
    const current = tabs.indexOf(event.target);
    if (current < 0) return;
    const moves = {ArrowRight:(current+1)%tabs.length, ArrowLeft:(current+tabs.length-1)%tabs.length,
      Home:0, End:tabs.length-1};
    if (event.key === ' ') {
      event.preventDefault();
      event.target.click();
    } else if (Object.hasOwn(moves,event.key)) {
      event.preventDefault();
      const next = tabs[moves[event.key]];
      next.focus();
      next.click();
    }
  });
}
function showProject(scroll) {
  let id;
  try { id = decodeURIComponent(location.hash.slice(1)); } catch { id = ''; }
  const target = document.getElementById(id);
  const project = projectPanels.find(panel => target && panel.contains(target)) ?? projectPanels[0];
  choose(projectTabs, projectPanels.indexOf(project));
  const sublist = project.querySelector('.subtabs');
  if (sublist) {
    const subtabs = [...sublist.querySelectorAll('[role="tab"]')];
    const panes = panelsFor(subtabs);
    const index = panes.findIndex(pane => target && pane.contains(target));
    choose(subtabs, Math.max(0,index));
    bindTabs(sublist);
  }
  const embed = project.querySelector('iframe[data-src]');
  if (embed && !embed.hasAttribute('src')) embed.src = embed.dataset.src;
  if (!scroll) return;
  const pane = target?.closest('[data-pane]');
  if (pane && target !== pane) target.scrollIntoView();
  else window.scrollTo(0,0);
}
bindTabs(projectTablist);
window.addEventListener('hashchange', () => showProject(true));
showProject(Boolean(location.hash));
