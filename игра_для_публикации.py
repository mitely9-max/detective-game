import http.server
import socketserver
import urllib.request
import json
import random
import webbrowser
import threading
import os
from datetime import date

PORT = int(os.environ.get("PORT", "8000"))
API_URL = "https://fakerapi.it/api/v1/persons?_quantity=4&_locale=ru_RU"

FALLBACK_SUSPECTS = [
    {"name": "Алексей Морозов", "gender": "male",   "age": 34, "city": "Москва",
     "country": "Russia", "nationality": "RU", "email": "a.morozov@example.com",
     "phone": "+7-900-111-22-33", "tz": "example.com"},
    {"name": "Елена Волкова",   "gender": "female", "age": 27, "city": "Санкт-Петербург",
     "country": "Russia", "nationality": "RU", "email": "e.volkova@example.com",
     "phone": "+7-900-222-33-44", "tz": "example.com"},
    {"name": "Дмитрий Соколов", "gender": "male",   "age": 48, "city": "Казань",
     "country": "Russia", "nationality": "RU", "email": "d.sokolov@mail.ru",
     "phone": "+7-900-333-44-55", "tz": "mail.ru"},
    {"name": "Ольга Лебедева",  "gender": "female", "age": 62, "city": "Новосибирск",
     "country": "Russia", "nationality": "RU", "email": "o.lebedeva@mail.ru",
     "phone": "+7-900-444-55-66", "tz": "mail.ru"},
]


def fetch_json(url, timeout=8):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DetectiveWeb/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _country_to_nat(country):
    mapping = {
        "Russia": "RU", "Germany": "DE", "France": "FR", "Italy": "IT",
        "Spain": "ES", "Netherlands": "NL", "Denmark": "DK", "Norway": "NO",
        "Finland": "FI", "United States": "US", "United Kingdom": "GB",
        "Poland": "PL", "Ukraine": "UA", "Belarus": "BY", "Kazakhstan": "KZ",
    }
    return mapping.get(country, country[:2].upper() if country else "XX")


def _calc_age(birthday_str):
    try:
        y, m, d = map(int, birthday_str.split("-"))
        today = date.today()
        return today.year - y - ((today.month, today.day) < (m, d))
    except Exception:
        return 30


def get_suspects():
    data = fetch_json(API_URL)
    if not data or "data" not in data or not data["data"]:
        return None

    suspects = []
    for p in data["data"]:
        addr = p.get("address", {}) or {}
        country = addr.get("country", "Unknown")
        email = p.get("email", "")
        domain = email.split("@")[-1] if "@" in email else "unknown"
        suspects.append({
            "name":        f"{p.get('firstname', '')} {p.get('lastname', '')}".strip(),
            "gender":      p.get("gender", "male"),
            "age":         _calc_age(p.get("birthday", "1990-01-01")),
            "city":        addr.get("city", "Unknown"),
            "country":     country,
            "nationality": _country_to_nat(country),
            "email":       email,
            "phone":       p.get("phone", "—"),
            "tz":          domain,
        })
    return suspects if len(suspects) >= 4 else None


def _age_bracket(age):
    if age < 30: return 0
    if age < 45: return 1
    if age < 60: return 2
    return 3


def clue_gender(c):
    g = c["gender"]; ru = "мужского пола" if g == "male" else "женского пола"
    return {"text": f"Свидетель показал: преступник был {ru}.",
            "check_id": ("gender", g)}

def clue_age(c):
    a = c["age"]; b = _age_bracket(a)
    labels = ["до 30 лет", "30–44 года", "45–59 лет", "60 лет и старше"]
    return {"text": f"Возраст преступника: {labels[b]}.", "check_id": ("age_bracket", b)}

def clue_city(c):
    return {"text": f"Обрывок билета ведёт в город: {c['city']}.", "check_id": ("city", c["city"])}

def clue_nationality(c):
    return {"text": f"Следы валюты указывают на гражданство: {c['nationality']}.",
            "check_id": ("nationality", c["nationality"])}

def clue_email_domain(c):
    return {"text": f"Восстановленный фрагмент переписки: домен почты преступника — {c['tz']}.",
            "check_id": ("tz", c["tz"])}

def clue_age_exact(c):
    return {"text": f"Судебная экспертиза установила точный возраст: {c['age']} лет.",
            "check_id": ("age", c["age"])}


def check(s, check_id):
    key, val = check_id
    if key == "gender":      return s["gender"] == val
    if key == "age":         return s["age"] == val
    if key == "age_bracket": return _age_bracket(s["age"]) == val
    if key == "city":        return s["city"] == val
    if key == "nationality": return s["nationality"] == val
    if key == "tz":          return s["tz"] == val
    if key == "id":          return s["_id"] == val
    return False


GENERATORS = [clue_gender, clue_age, clue_city, clue_nationality, clue_email_domain, clue_age_exact]


def _useful_true(clue, culprit, suspects):
    if not check(culprit, clue["check_id"]):
        return False
    return any(not check(s, clue["check_id"]) for s in suspects if s is not culprit)


def build_truthful_clues(culprit, suspects):
    cands = []
    for gen in GENERATORS:
        try:
            c = gen(culprit)
        except Exception:
            continue
        if _useful_true(c, culprit, suspects):
            c["truthful"] = True
            cands.append(c)
    random.shuffle(cands)
    selected = cands[:5]
    rem = list(suspects)
    for c in selected:
        rem = [s for s in rem if check(s, c["check_id"])]
    if len(rem) > 1:
        selected.append({
            "text": f"Отпечаток пальца принадлежит: {culprit['name']}.",
            "check_id": ("id", culprit["_id"]),
            "truthful": True,
        })
    return selected


def build_false_clue(culprit, suspects):
    innocents = [s for s in suspects if s is not culprit]
    if not innocents:
        return None
    cands = []

    for g in ({s["gender"] for s in innocents} - {culprit["gender"]}):
        ru = "мужского пола" if g == "male" else "женского пола"
        cands.append({"text": f"Анонимный источник: преступник был {ru}.",
                      "check_id": ("gender", g)})

    for city in ({s["city"] for s in innocents} - {culprit["city"]}):
        cands.append({"text": f"Найдена квитанция такси до города: {city}.",
                      "check_id": ("city", city)})

    cb = _age_bracket(culprit["age"])
    for s in innocents:
        ib = _age_bracket(s["age"])
        if ib != cb:
            labels = ["до 30 лет", "30–44 года", "45–59 лет", "60 лет и старше"]
            cands.append({"text": f"Аноним: возраст преступника — {labels[ib]}.",
                          "check_id": ("age_bracket", ib)})
            break

    for n in ({s["nationality"] for s in innocents} - {culprit["nationality"]}):
        cands.append({"text": f"Слух в баре: преступник — гражданин {n}.",
                      "check_id": ("nationality", n)})

    for d in ({s["tz"] for s in innocents} - {culprit["tz"]}):
        cands.append({"text": f"Фальшивый след: домен почты преступника — {d}.",
                      "check_id": ("tz", d)})

    if not cands:
        return None
    c = random.choice(cands)
    c["truthful"] = False
    return c


def build_case():
    suspects = get_suspects()
    if not suspects:
        suspects = [dict(s) for s in FALLBACK_SUSPECTS]

    random.shuffle(suspects)
    for i, s in enumerate(suspects):
        s["_id"] = i
    culprit = random.choice(suspects)

    truthful = build_truthful_clues(culprit, suspects)
    false_c = build_false_clue(culprit, suspects)
    all_clues = truthful + ([false_c] if false_c else [])
    random.shuffle(all_clues)
    for i, c in enumerate(all_clues):
        if not c["truthful"] and i == 0 and len(all_clues) > 2:
            all_clues[0], all_clues[1] = all_clues[1], all_clues[0]
            break

    return {
        "suspects": suspects,
        "culprit_id": culprit["_id"],
        "clues": [
            {"text": c["text"],
             "check_id": list(c["check_id"]) if c["check_id"][0] != "id" else ["id", c["check_id"][1]],
             "truthful": c["truthful"]}
            for c in all_clues
        ],
    }


HTML_PAGE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Детектив — дело о похищенном шедевре</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #0f1117; --panel: #171a23; --panel2: #1f2430;
    --line: #2a3040; --ink: #e6e9f0; --dim: #97a0b5;
    --accent: #d4a24c; --danger: #e05a5a; --ok: #4caf7d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: ui-serif, Georgia, "Times New Roman", serif;
    background: radial-gradient(1200px 600px at 20% -10%, #1a1f2d 0%, var(--bg) 60%);
    color: var(--ink); min-height: 100vh;
  }
  header {
    border-bottom: 1px solid var(--line); padding: 20px 24px;
    display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap;
  }
  header h1 { margin: 0; font-size: 22px; letter-spacing: 0.5px; }
  header .sub { color: var(--dim); font-size: 13px; }
  main { max-width: 1180px; margin: 0 auto; padding: 20px 24px 80px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }

  .card {
    background: linear-gradient(180deg, var(--panel) 0%, #141823 100%);
    border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px;
  }
  .card h2 { margin: 0 0 12px; font-size: 16px; color: var(--accent); letter-spacing: 0.5px; }
  .toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  button {
    font: inherit; cursor: pointer; border-radius: 8px;
    border: 1px solid var(--line); background: var(--panel2); color: var(--ink);
    padding: 8px 14px; transition: background 0.15s, border 0.15s, transform 0.05s;
  }
  button:hover:not(:disabled) { background: #262c3b; border-color: #3b4458; }
  button:active:not(:disabled) { transform: translateY(1px); }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.primary { background: #3b2e17; border-color: #6b5226; color: #f0d9a5; }
  button.primary:hover:not(:disabled) { background: #4a3a1d; }

  .suspect {
    display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center;
    padding: 12px 10px; border-radius: 10px; margin-bottom: 8px;
    background: var(--panel2); border: 1px solid transparent; transition: border 0.15s;
  }
  .suspect:hover { border-color: var(--line); }
  .suspect.eliminated { opacity: 0.5; }
  .suspect .name { font-weight: 700; }
  .suspect .meta { color: var(--dim); font-size: 13px; margin-top: 2px; }
  .suspect .tag { color: var(--ok); font-size: 12px; }
  .suspect .actions button { padding: 6px 10px; font-size: 13px; }

  .clue {
    padding: 12px 12px; border-left: 3px solid var(--accent);
    background: var(--panel2); border-radius: 6px; margin-bottom: 8px;
    animation: fadeIn 0.35s ease;
  }
  .clue.verified-true  { border-left-color: var(--ok); }
  .clue.verified-false { border-left-color: var(--danger); }
  .clue .row { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
  .clue .num { color: var(--accent); font-size: 12px; letter-spacing: 0.5px; }
  .clue .badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
  .clue .badge.true  { background: #1d3529; color: #7fd8a8; }
  .clue .badge.false { background: #3a1e1e; color: #f09a9a; }

  .empty { color: var(--dim); font-style: italic; }
  .sys {
    color: var(--accent); font-size: 13px; padding: 10px 12px;
    border: 1px dashed var(--line); border-radius: 8px; margin: 10px 0;
    animation: fadeIn 0.4s ease;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; } }

  dialog {
    border: 1px solid var(--line); border-radius: 14px; background: var(--panel);
    color: var(--ink); max-width: 540px; padding: 22px 24px;
  }
  dialog::backdrop { background: rgba(0,0,0,0.7); }
  dialog h3 { margin: 0 0 12px; }
  dialog.win h3  { color: var(--ok); }
  dialog.fail h3 { color: var(--danger); }
  dialog p { margin: 8px 0; color: var(--ink); }
  dialog .quote { color: var(--dim); font-style: italic; padding-left: 10px;
                  border-left: 2px solid var(--line); margin: 8px 0; }
  footer { color: var(--dim); font-size: 12px; text-align: center; padding: 24px 0; }
</style>
</head>
<body>

<header>
  <h1>🕵️ Дело о похищенном шедевре</h1>
  <span class="sub" id="sourceLabel"></span>
</header>

<main>
  <div class="toolbar" style="margin-bottom:20px;">
    <button class="primary" onclick="newCase()">Новое дело</button>
    <button onclick="revealClue()">Следующая улика</button>
    <button onclick="verifyClue()" id="btnVerifyClue">Проверить улику (2)</button>
    <button onclick="verifyAlibi()" id="btnVerifyAlibi">Проверить алиби (2)</button>
  </div>

  <div class="grid">
    <div>
      <div class="card">
        <h2>Подозреваемые</h2>
        <div id="suspects"></div>
      </div>
      <div id="messages" style="margin-top:12px;"></div>
    </div>
    <div>
      <div class="card">
        <h2>Улики</h2>
        <div id="clues" class="empty">Улик пока нет — нажмите «Следующая улика».</div>
      </div>
    </div>
  </div>
</main>

<footer>Детективное агентство «Тень» · Все совпадения случайны</footer>

<dialog id="resultDialog">
  <h3 id="dlgTitle"></h3>
  <div id="dlgBody"></div>
  <div style="text-align:right; margin-top:16px;">
    <button class="primary" onclick="closeAndNew()">Новое дело</button>
  </div>
</dialog>

<script>
let state = null;

function ageBracket(a) { return a<30?0:a<45?1:a<60?2:3; }

function check(s, checkId) {
  const [key, val] = checkId;
  if (key === "gender")      return s.gender === val;
  if (key === "age")         return s.age === val;
  if (key === "age_bracket") return ageBracket(s.age) === val;
  if (key === "city")        return s.city === val;
  if (key === "nationality") return s.nationality === val;
  if (key === "tz")          return s.tz === val;
  if (key === "id")          return s._id === val;
  return false;
}

async function newCase() {
  document.getElementById("suspects").innerHTML = '<div class="empty">Загрузка...</div>';
  document.getElementById("clues").innerHTML = '<div class="empty">Загрузка...</div>';
  document.getElementById("messages").innerHTML = "";
  try {
    const r = await fetch("/api/new-case");
    const data = await r.json();
    state = {
      suspects: data.suspects,
      clues: [], allClues: data.clues,
      revealed: 0, verified: {},
      eliminated: new Set(),
      verificationsLeft: 2, alibiLeft: 2,
      finished: false,
      twistShown: false, contradictionShown: false,
    };
    document.getElementById("sourceLabel").textContent = "Материалы дела засекречены";
    render();
  } catch (e) {
    document.getElementById("suspects").innerHTML = '<div class="empty">Не удалось открыть материалы дела. Попробуйте ещё раз.</div>';
  }
}

function render() {
  if (!state) return;
  const sBox = document.getElementById("suspects");
  sBox.innerHTML = "";
  state.suspects.forEach((s, i) => {
    const eliminated = state.eliminated.has(s._id);
    const el = document.createElement("div");
    el.className = "suspect" + (eliminated ? " eliminated" : "");
    el.innerHTML = `
      <div>
        <div class="name">${i+1}. ${s.name}</div>
        <div class="meta">${s.age} лет · ${s.city}, ${s.country} · ${s.nationality}</div>
        ${eliminated ? `<div class="tag">✓ алиби подтверждено</div>` : ""}
      </div>
      <div class="actions">
        <button ${state.finished?'disabled':''} onclick="accuse(${s._id})">Обвинить</button>
      </div>
    `;
    sBox.appendChild(el);
  });

  const cBox = document.getElementById("clues");
  if (!state.clues.length) {
    cBox.className = "empty";
    cBox.textContent = "Улик пока нет — нажмите «Следующая улика».";
  } else {
    cBox.className = "";
    cBox.innerHTML = "";
    state.clues.forEach((c, i) => {
      const v = state.verified[i];
      const div = document.createElement("div");
      div.className = "clue" + (v === true ? " verified-true" : v === false ? " verified-false" : "");
      let badge = "";
      if (v === true)  badge = `<span class="badge true">правдива</span>`;
      if (v === false) badge = `<span class="badge false">ложь</span>`;
      div.innerHTML = `
        <div class="row">
          <span class="num">УЛИКА #${i+1}</span>
          ${badge}
        </div>
        <div style="margin-top:6px;">${c.text}</div>
      `;
      cBox.appendChild(div);
    });
  }

  document.getElementById("btnVerifyClue").disabled  = state.verificationsLeft <= 0 || state.revealed === 0 || state.finished;
  document.getElementById("btnVerifyAlibi").disabled = state.alibiLeft <= 0 || state.finished;
  document.getElementById("btnVerifyClue").textContent  = `Проверить улику (${state.verificationsLeft})`;
  document.getElementById("btnVerifyAlibi").textContent = `Проверить алиби (${state.alibiLeft})`;
}

function addMessage(text) {
  const box = document.getElementById("messages");
  const div = document.createElement("div");
  div.className = "sys";
  div.textContent = text;
  box.appendChild(div);
}

function revealClue() {
  if (!state || state.finished) return;
  if (state.revealed >= state.allClues.length) {
    addMessage("Все улики собраны. Пора выдвигать обвинение.");
    return;
  }
  const c = state.allClues[state.revealed];
  state.clues.push(c);
  state.revealed++;

  if (state.revealed === 3 && !state.twistShown) {
    state.twistShown = true;
    setTimeout(() => addMessage("📞 Анонимный звонок: «Детектив, не всем уликам можно верить...»"), 300);
  }
  if (state.revealed === state.allClues.length && !state.contradictionShown) {
    state.contradictionShown = true;
    let m = state.suspects.slice();
    state.clues.forEach(c => { m = m.filter(s => check(s, c.check_id)); });
    if (!m.length) {
      setTimeout(() => addMessage("🔍 Задумайтесь: если верить ВСЕМ уликам, подозреваемых не остаётся вообще. Одна из улик — ЛОЖНАЯ."), 300);
    }
  }
  render();
}

function verifyClue() {
  if (!state || state.finished || state.verificationsLeft <= 0 || !state.clues.length) return;
  const idx = prompt(`Какую улику проверить? (1–${state.clues.length})`);
  if (idx === null) return;
  const n = parseInt(idx, 10);
  if (isNaN(n) || n < 1 || n > state.clues.length) { alert("Неверный номер."); return; }
  const i = n - 1;
  if (state.verified[i] !== undefined) { alert("Эта улика уже проверена."); return; }
  state.verificationsLeft--;
  const truthful = state.clues[i].truthful;
  state.verified[i] = truthful;
  addMessage(truthful
    ? `[Проверка улики #${n}] Улика правдива. Источник надёжен.`
    : `[Проверка улики #${n}] ⚠ Улика ЛОЖНА. Источник вводил в заблуждение.`);
  render();
}

function verifyAlibi() {
  if (!state || state.finished || state.alibiLeft <= 0) return;
  const idx = prompt(`Чьё алиби проверить? (1–${state.suspects.length})`);
  if (idx === null) return;
  const n = parseInt(idx, 10);
  if (isNaN(n) || n < 1 || n > state.suspects.length) { alert("Неверный номер."); return; }
  const s = state.suspects[n - 1];
  if (state.eliminated.has(s._id)) { alert("Алиби уже подтверждено."); return; }
  state.alibiLeft--;
  fetch("/api/check-alibi", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ suspect_id: s._id }) })
    .then(r => r.json())
    .then(data => {
      if (data.alibi) {
        state.eliminated.add(s._id);
        addMessage(`[Проверка алиби #${n}] Алиби подтверждено: ${s.name} был(а) в другом месте.`);
      } else {
        addMessage(`[Проверка алиби #${n}] ${s.name} утверждает, что был(а) дома один(а). Свидетелей нет. Не алиби.`);
      }
      render();
    });
}

function accuse(suspectId) {
  if (!state || state.finished) return;
  const s = state.suspects.find(x => x._id === suspectId);
  fetch("/api/accuse", { method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ suspect_id: suspectId }) })
    .then(r => r.json())
    .then(data => {
      state.finished = true;
      const dlg = document.getElementById("resultDialog");
      const title = document.getElementById("dlgTitle");
      const body = document.getElementById("dlgBody");
      dlg.classList.remove("win", "fail");

      if (data.correct) {
        dlg.classList.add("win");
        title.textContent = `✔ Дело раскрыто: ${s.name} виновен`;
        const score = Math.max(10, 100 - state.revealed*6 - (2-state.verificationsLeft)*10 - (2-state.alibiLeft)*8);
        let html = `<p>Вы предъявили обвинение, и оно подтвердилось.</p>`;
        html += `<p>Улик собрано: ${state.revealed}. Проверок улик: ${2-state.verificationsLeft}, проверок алиби: ${2-state.alibiLeft}.</p>`;
        html += `<p><b>Итоговый счёт: ${score}/100.</b></p>`;
        const falseIdx = state.clues.findIndex(c => !c.truthful);
        if (falseIdx !== -1) {
          html += `<p>Кстати, улика #${falseIdx+1} была ложной:</p>
                   <div class="quote">«${state.clues[falseIdx].text}»</div>
                   <p>— кто-то подбросил её, чтобы сбить следствие.</p>`;
        }
        body.innerHTML = html;
      } else {
        dlg.classList.add("fail");
        title.textContent = `✘ Дело провалено: ${s.name} невиновен`;
        const culprit = state.suspects.find(x => x._id === data.culprit_id);
        let html = "";
        const falseIdx = state.clues.findIndex(c => !c.truthful);
        if (falseIdx !== -1) {
          html += `<p>Вы поверили улике #${falseIdx+1}:</p>
                   <div class="quote">«${state.clues[falseIdx].text}»</div>
                   <p>— а она оказалась ложной. Ловушка сработала.</p>`;
        }
        html += `<p>Настоящий преступник: <b>${culprit ? culprit.name : "неизвестен"}</b>.</p>`;
        body.innerHTML = html;
      }
      dlg.showModal();
      render();
    });
}

function closeAndNew() {
  document.getElementById("resultDialog").close();
  newCase();
}

newCase();
</script>
</body>
</html>
"""


CURRENT_CASE = {"culprit_id": None, "suspects": [], "clues": []}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(HTML_PAGE)
        elif self.path == "/api/new-case":
            case = build_case()
            CURRENT_CASE["culprit_id"] = case["culprit_id"]
            CURRENT_CASE["suspects"] = case["suspects"]
            CURRENT_CASE["clues"] = case["clues"]
            safe = {
                "suspects": [{k: v for k, v in s.items()} for s in case["suspects"]],
                "clues": [{"text": c["text"], "check_id": c["check_id"]} for c in case["clues"]],
            }
            self._send_json(safe)
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception:
            self._send_json({"error": "bad request"}, 400)
            return

        if self.path == "/api/check-alibi":
            sid = body.get("suspect_id")
            culprit_id = CURRENT_CASE["culprit_id"]
            is_innocent = (sid is not None and sid != culprit_id)
            self._send_json({"alibi": bool(is_innocent)})
        elif self.path == "/api/accuse":
            sid = body.get("suspect_id")
            correct = (sid == CURRENT_CASE["culprit_id"])
            self._send_json({"correct": correct, "culprit_id": CURRENT_CASE["culprit_id"]})
        else:
            self.send_error(404)


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run():
    with ReusableTCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}"
        print("=" * 56)
        print("  Детектив — веб-версия запущена")
        print(f"  Откройте в браузере: {url}")
        print("  Ctrl+C — остановить сервер")
        print("=" * 56)
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nСервер остановлен.")


if __name__ == "__main__":
    run()