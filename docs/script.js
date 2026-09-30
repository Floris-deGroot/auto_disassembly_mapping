// Small extras. The page works fine without this file.

// Copy buttons on code blocks
document.querySelectorAll("pre > code").forEach((code) => {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "copy";
  btn.textContent = "Copy";
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code.innerText.trim());
      btn.textContent = "Copied";
    } catch {
      btn.textContent = "Select to copy";
    }
    setTimeout(() => (btn.textContent = "Copy"), 1500);
  });
  code.parentElement.appendChild(btn);
});

// macOS / Windows / Linux tabs, synced across the page
const OSES = ["macOS", "Windows", "Linux"];
const groups = [...document.querySelectorAll(".os-group")];

function detectOS() {
  try {
    const saved = localStorage.getItem("os");
    if (OSES.includes(saved)) return saved;
  } catch {}
  const p = (navigator.userAgentData?.platform || navigator.platform || navigator.userAgent).toLowerCase();
  if (p.includes("win")) return "Windows";
  if (p.includes("linux") && !p.includes("android")) return "Linux";
  return "macOS";
}

function selectOS(os) {
  try { localStorage.setItem("os", os); } catch {}
  groups.forEach((g) => {
    g.querySelectorAll(".os-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.os === os)));
    g.querySelectorAll("pre[data-os]").forEach((pre) => (pre.hidden = !pre.dataset.os.split(" ").includes(os)));
  });
}

groups.forEach((g) => {
  const bar = document.createElement("div");
  bar.className = "os-tabs";
  bar.setAttribute("role", "tablist");
  bar.setAttribute("aria-label", "Operating system");
  OSES.forEach((os) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = os;
    b.dataset.os = os;
    b.setAttribute("role", "tab");
    b.addEventListener("click", () => selectOS(os));
    bar.appendChild(b);
  });
  g.prepend(bar);
  g.classList.add("js");
});
if (groups.length) selectOS(detectOS());

// Highlight the current section in the top bar
const links = new Map(
  [...document.querySelectorAll('.topbar nav a[href^="#"]')].map((a) => [a.getAttribute("href").slice(1), a])
);
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        links.forEach((a) => a.removeAttribute("aria-current"));
        links.get(e.target.id)?.setAttribute("aria-current", "true");
      });
    },
    { rootMargin: "-40% 0px -55% 0px" }
  );
  links.forEach((_, id) => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
}
