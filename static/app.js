(() => {
  "use strict";

  const PALETTE = ["#2a78d6", "#0ca35f", "#d98c00", "#d03b3b", "#7c5cd6", "#0891b2", "#c2456b", "#4b5563"];

  let currentData = null;
  let selectedStmt = "is";
  let selectedItems = { is: new Set(), bs: new Set(), cf: new Set() };
  let ratioMapping = {};

  const $ = (id) => document.getElementById(id);

  // ---------------- 인쇄 / 이미지 저장 ----------------

  document.addEventListener("click", (e) => {
    const printBtn = e.target.closest("[data-print]");
    if (printBtn) {
      window.print();
      return;
    }
    const saveBtn = e.target.closest("[data-save-img]");
    if (saveBtn) {
      const container = $(saveBtn.dataset.saveImg);
      const svg = container && container.querySelector("svg");
      if (svg) saveSvgAsPng(svg, saveBtn.dataset.filename || "chart");
    }
  });

  function saveSvgAsPng(svgEl, filenameBase) {
    const clone = svgEl.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");

    // var(--token) 참조는 별도 문서 컨텍스트(Image)에서 해석되지 않으므로
    // 현재 테마의 실제 색상 값으로 치환해 저장한다.
    const cs = getComputedStyle(document.documentElement);
    const tokens = ["--text", "--text-dim", "--text-faint", "--border", "--surface"];
    const resolved = {};
    tokens.forEach((t) => { resolved[t] = cs.getPropertyValue(t).trim(); });
    ["fill", "stroke"].forEach((attr) => {
      clone.querySelectorAll(`[${attr}]`).forEach((el) => {
        const v = el.getAttribute(attr);
        const m = v && v.match(/^var\((--[a-z-]+)\)$/);
        if (m && resolved[m[1]]) el.setAttribute(attr, resolved[m[1]]);
      });
    });

    const bg = resolved["--surface"] || "#ffffff";
    const { width, height } = svgEl.getBoundingClientRect();
    const w = Math.max(Math.round(width), 1);
    const h = Math.max(Math.round(height), 1);
    clone.setAttribute("width", w);
    clone.setAttribute("height", h);

    const svgStr = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);

    const img = new Image();
    img.onload = () => {
      const scale = 2; // 저장 화질(레티나 대응)
      const canvas = document.createElement("canvas");
      canvas.width = w * scale;
      canvas.height = h * scale;
      const ctx = canvas.getContext("2d");
      ctx.scale(scale, scale);
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => {
        const a = document.createElement("a");
        const stamp = new Date().toISOString().slice(0, 10);
        a.href = URL.createObjectURL(blob);
        a.download = `${filenameBase}_${(currentData && currentData.corp_name) || ""}_${stamp}.png`;
        a.click();
      });
    };
    img.src = url;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  function setStatus(msg, isError = false) {
    const bar = $("statusBar");
    bar.textContent = msg;
    bar.hidden = false;
    bar.classList.toggle("error", isError);
  }

  function clearStatus() {
    const bar = $("statusBar");
    bar.hidden = true;
    bar.classList.remove("error");
  }

  // ---------------- 검색 ----------------

  $("searchForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("searchInput").value.trim();
    if (!q) return;
    setStatus("검색 중...");
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      clearStatus();
      renderSearchResults(data.matches);
    } catch (err) {
      setStatus("검색 실패: " + err.message, true);
    }
  });

  function renderSearchResults(matches) {
    const box = $("searchResults");
    box.innerHTML = "";
    if (!matches.length) {
      box.innerHTML = '<p class="hint">검색 결과가 없습니다. 정확한 회사명을 입력해보세요.</p>';
      return;
    }
    matches.forEach((m) => {
      const div = document.createElement("div");
      div.className = "search-result-item";
      div.tabIndex = 0;
      div.innerHTML = `<span>${escapeHtml(m.corp_name)}</span><span class="code">${escapeHtml(m.stock_code || m.corp_code)}</span>`;
      div.addEventListener("click", () => loadCompany(m.corp_code));
      div.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); loadCompany(m.corp_code); }
      });
      box.appendChild(div);
    });
  }

  // ---------------- 회사 데이터 로드 ----------------

  const POLL_INTERVAL_MS = 4000;
  const POLL_TIMEOUT_MS = 4 * 60 * 1000;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function loadCompany(code) {
    $("searchResults").innerHTML = "";
    $("companyPanel").hidden = true;
    setStatus("재무제표를 불러오는 중입니다... DART 최초 조회는 1~3분 정도 걸릴 수 있어요.");
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    try {
      while (true) {
        const res = await fetch(`/api/company/${encodeURIComponent(code)}`);
        if (res.status === 202) {
          if (Date.now() > deadline) throw new Error("시간 초과 (분석이 너무 오래 걸립니다)");
          await sleep(POLL_INTERVAL_MS);
          continue;
        }
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        currentData = await res.json();
        break;
      }
      clearStatus();
      renderCompany();
    } catch (err) {
      setStatus("조회 실패: " + err.message, true);
    }
  }

  function renderCompany() {
    $("companyPanel").hidden = false;
    $("companyName").textContent = currentData.corp_name;
    $("industryBadge").textContent = currentData.industry.세부업종 || "업종 미상";

    selectedItems = { is: new Set(), bs: new Set(), cf: new Set() };
    ratioMapping = {};

    selectedStmt = "is";
    document.querySelectorAll(".sub-tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.stmt === "is"));
    renderItemChips();
    $("indicatorChartPanel").hidden = true;
    $("drawIndicatorBtn").disabled = true;

    renderRatioCards();
    renderAccountPool();
    $("ratioChartPanel").hidden = true;
    $("computeRatiosBtn").disabled = true;
  }

  // ---------------- 메인 탭 ----------------

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      $("indicatorTab").hidden = tab !== "indicator";
      $("ratioTab").hidden = tab !== "ratio";
    });
  });

  document.querySelectorAll(".sub-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sub-tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedStmt = btn.dataset.stmt;
      renderItemChips();
    });
  });

  // ---------------- 원본 지표 그래프 ----------------

  function renderItemChips() {
    const box = $("itemChips");
    box.innerHTML = "";
    const stmt = currentData.statements[selectedStmt];
    if (!stmt || !stmt.items.length) {
      box.innerHTML = `<p class="hint">${stmt && stmt.error ? escapeHtml(stmt.error) : "데이터가 없습니다."}</p>`;
      return;
    }
    stmt.items.forEach((item) => {
      const chip = document.createElement("div");
      chip.className = "chip" + (selectedItems[selectedStmt].has(item.label) ? " selected" : "");
      chip.textContent = item.label;
      chip.tabIndex = 0;
      const toggle = () => {
        if (selectedItems[selectedStmt].has(item.label)) selectedItems[selectedStmt].delete(item.label);
        else selectedItems[selectedStmt].add(item.label);
        chip.classList.toggle("selected");
        $("drawIndicatorBtn").disabled = selectedItems[selectedStmt].size === 0;
      };
      chip.addEventListener("click", toggle);
      chip.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      });
      box.appendChild(chip);
    });
  }

  $("drawIndicatorBtn").addEventListener("click", () => {
    const stmt = currentData.statements[selectedStmt];
    const labels = [...selectedItems[selectedStmt]];
    const series = labels
      .map((label) => stmt.items.find((i) => i.label === label))
      .filter(Boolean)
      .map((item) => ({ label: item.label, values: item.values }));

    $("indicatorChartPanel").hidden = false;
    renderIndicatorChart(series, stmt.years);
  });

  function formatKR(v) {
    const abs = Math.abs(v);
    if (abs >= 1e12) return (v / 1e12).toFixed(2) + "조";
    if (abs >= 1e8) return (v / 1e8).toFixed(2) + "억";
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function pickScale(maxAbs) {
    if (!isFinite(maxAbs) || maxAbs === 0) return { divisor: 1e12, unit: "조 원" };
    if (maxAbs >= 1e12) return { divisor: 1e12, unit: "조 원" };
    if (maxAbs >= 1e8) return { divisor: 1e8, unit: "억 원" };
    return { divisor: 1, unit: "원" };
  }

  function renderIndicatorChart(series, years) {
    let maxAbs = 0;
    series.forEach((s) => years.forEach((y) => {
      const v = s.values[y];
      if (v !== undefined) maxAbs = Math.max(maxAbs, Math.abs(v));
    }));
    const { divisor, unit } = pickScale(maxAbs);

    const chartSeries = series.map((s, i) => ({
      label: s.label,
      color: PALETTE[i % PALETTE.length],
      points: years
        .filter((y) => s.values[y] !== undefined)
        .map((y) => ({ x: y, y: s.values[y] / divisor, raw: s.values[y] })),
    }));

    drawLineChart($("indicatorChart"), chartSeries, years, {
      yAxisLabel: `금액 (단위: ${unit})`,
      pointLabel: (pt) => formatKR(pt.raw),
    });
  }

  // ---------------- 업종 추천 비율 (드래그앤드롭) ----------------

  function renderRatioCards() {
    const box = $("ratioCards");
    box.innerHTML = "";

    currentData.recommended_ratios.forEach((r) => {
      const card = document.createElement("div");

      if (!r.계산가능) {
        card.className = "ratio-card disabled";
        card.innerHTML = `
          <div class="rc-title">${escapeHtml(r.이름)} <span class="rc-unit">⚠️ 계산 불가</span></div>
          <div class="rc-note">${escapeHtml(r.비고)}</div>`;
        box.appendChild(card);
        return;
      }

      card.className = "ratio-card";
      card.innerHTML = `
        <div class="rc-title">${escapeHtml(r.이름)} <span class="rc-unit">단위: ${escapeHtml(r.단위)}</span></div>
        <div class="rc-slots">
          <div class="drop-zone" data-key="${r.key}" data-slot="num">
            <span><span class="dz-label">${escapeHtml(r.분자설명)} (${r.분자출처})</span>여기로 드래그</span>
          </div>
          <span class="slash">/</span>
          <div class="drop-zone" data-key="${r.key}" data-slot="den">
            <span><span class="dz-label">${escapeHtml(r.분모설명)} (${r.분모출처})</span>여기로 드래그</span>
          </div>
        </div>`;
      box.appendChild(card);
    });

    box.querySelectorAll(".drop-zone").forEach((zone) => {
      zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
      zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        let data;
        try {
          data = JSON.parse(e.dataTransfer.getData("text/plain"));
        } catch {
          return;
        }
        const key = zone.dataset.key;
        const slot = zone.dataset.slot;
        ratioMapping[key] = ratioMapping[key] || {};
        ratioMapping[key][slot] = data;

        zone.classList.add("filled");
        zone.innerHTML = `<span><span class="dz-label">${slot === "num" ? "분자" : "분모"}</span>${escapeHtml(data.label)}</span>`;
        updateComputeButton();
      });
    });
  }

  function renderAccountPool() {
    renderPool("poolBs", currentData.statements.bs, "BS");
    renderPool("poolIs", currentData.statements.is, "IS");
  }

  function renderPool(elId, stmt, sourceTag) {
    const box = $(elId);
    box.innerHTML = "";
    if (!stmt || !stmt.items.length) {
      box.innerHTML = '<p class="hint">데이터가 없습니다.</p>';
      return;
    }
    stmt.items.forEach((item) => {
      const chip = document.createElement("div");
      chip.className = "chip draggable-chip";
      chip.textContent = item.label;
      chip.draggable = true;
      chip.addEventListener("dragstart", (e) => {
        chip.classList.add("dragging");
        e.dataTransfer.setData("text/plain", JSON.stringify({ label: item.label, source: sourceTag, values: item.values }));
      });
      chip.addEventListener("dragend", () => chip.classList.remove("dragging"));
      box.appendChild(chip);
    });
  }

  function updateComputeButton() {
    const anyFilled = Object.values(ratioMapping).some((m) => m && m.num && m.den);
    $("computeRatiosBtn").disabled = !anyFilled;
  }

  $("computeRatiosBtn").addEventListener("click", () => {
    const results = {};
    currentData.recommended_ratios.forEach((r) => {
      const m = ratioMapping[r.key];
      if (!m || !m.num || !m.den) return;

      const series = {};
      Object.keys(m.num.values).forEach((y) => {
        const den = m.den.values[y];
        if (den === undefined || den === 0) return;
        const raw = m.num.values[y] / den;
        series[y] = r.단위 === "%" ? raw * 100 : raw;
      });

      if (Object.keys(series).length) {
        results[r.key] = { name: r.이름, unit: r.단위, series };
      }
    });
    renderRatioResults(results);
  });

  function renderRatioResults(results) {
    const keys = Object.keys(results);
    $("ratioChartPanel").hidden = keys.length === 0;
    if (!keys.length) {
      $("ratioTable").innerHTML = '<p class="hint">분자/분모가 모두 채워진 비율이 없습니다.</p>';
      return;
    }

    const yearsSet = new Set();
    keys.forEach((k) => Object.keys(results[k].series).forEach((y) => yearsSet.add(y)));
    const years = [...yearsSet].sort();

    const series = keys.map((k, i) => ({
      label: `${results[k].name} (${results[k].unit})`,
      color: PALETTE[i % PALETTE.length],
      points: years
        .filter((y) => results[k].series[y] !== undefined)
        .map((y) => ({ x: y, y: results[k].series[y], raw: results[k].series[y] })),
    }));

    drawLineChart($("ratioChart"), series, years, {
      yAxisLabel: "비율 값 (%, 배 혼합 — 범례 참조)",
      pointLabel: (pt) => pt.raw.toFixed(2),
    });

    let html = '<table class="ratio-table"><thead><tr><th>비율</th>' + years.map((y) => `<th>${y}</th>`).join("") + "</tr></thead><tbody>";
    keys.forEach((k) => {
      const unitSuffix = results[k].unit === "%" ? "%" : "배";
      html += `<tr><td>${escapeHtml(results[k].name)} (${escapeHtml(results[k].unit)})</td>` +
        years.map((y) => {
          const v = results[k].series[y];
          return v === undefined ? "<td>-</td>" : `<td>${v.toFixed(2)}${unitSuffix}</td>`;
        }).join("") + "</tr>";
    });
    html += "</tbody></table>";
    $("ratioTable").innerHTML = html;
  }

  // ---------------- 공용 SVG 라인 차트 ----------------

  function formatAxisNum(v) {
    return Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
  }

  function drawLineChart(container, series, years, opts) {
    const W = 860, H = 380, padL = 64, padR = 20, padT = 28, padB = 40;
    const innerW = W - padL - padR, innerH = H - padT - padB;

    const allY = [];
    series.forEach((s) => s.points.forEach((p) => allY.push(p.y)));
    if (!allY.length) {
      container.innerHTML = '<p class="hint">표시할 데이터가 없습니다.</p>';
      return;
    }

    let minY = Math.min(0, ...allY);
    let maxY = Math.max(...allY);
    if (minY === maxY) { maxY += 1; minY -= 1; }
    const pad = (maxY - minY) * 0.15;
    maxY += pad;
    if (minY < 0) minY -= pad;

    const xPos = (year) => padL + (years.indexOf(year) / Math.max(years.length - 1, 1)) * innerW;
    const yPos = (val) => padT + innerH - ((val - minY) / (maxY - minY)) * innerH;

    let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
    svg += `<text x="${padL}" y="16" font-size="11.5" font-weight="700" fill="var(--text-dim)">${escapeHtml(opts.yAxisLabel || "")}</text>`;

    const gridSteps = 5;
    for (let i = 0; i <= gridSteps; i++) {
      const val = minY + (maxY - minY) * (i / gridSteps);
      const y = yPos(val);
      svg += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--border)" stroke-dasharray="3,3" />`;
      svg += `<text x="${padL - 8}" y="${y + 4}" text-anchor="end" font-size="10.5" fill="var(--text-faint)">${formatAxisNum(val)}</text>`;
    }

    years.forEach((y) => {
      const x = xPos(y);
      svg += `<text x="${x}" y="${H - padB + 18}" text-anchor="middle" font-size="10.5" fill="var(--text-faint)">${y}</text>`;
    });

    series.forEach((s, si) => {
      if (!s.points.length) return;
      const path = s.points.map((p, idx) => `${idx === 0 ? "M" : "L"} ${xPos(p.x)} ${yPos(p.y)}`).join(" ");
      svg += `<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.4" />`;
      s.points.forEach((p) => {
        const cx = xPos(p.x), cy = yPos(p.y);
        svg += `<circle cx="${cx}" cy="${cy}" r="3.6" fill="${s.color}" />`;
        if (opts.pointLabel) {
          const dy = si % 2 === 0 ? -10 : 18;
          svg += `<text x="${cx}" y="${cy + dy}" text-anchor="middle" font-size="9.5" fill="${s.color}" font-weight="700">${escapeHtml(opts.pointLabel(p))}</text>`;
        }
      });
    });

    svg += "</svg>";

    let legend = '<div class="legend">';
    series.forEach((s) => {
      legend += `<div class="legend-item"><span class="legend-swatch" style="background:${s.color}"></span>${escapeHtml(s.label)}</div>`;
    });
    legend += "</div>";

    container.innerHTML = svg + legend;
  }
})();
