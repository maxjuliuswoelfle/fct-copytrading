/**
 * (C) app.js — Copy Trading Dashboard v3.0
 * Live-Polling, Echtzeit-Updates, Equity Chart mit echten Daten
 */

(function () {
    'use strict';

    // ============================================================
    // HELPERS
    // ============================================================

    function fmtNum(v, d) {
        d = d || 2;
        return v.toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });
    }
    function fmtPct(v) { return (v >= 0 ? '+' : '−') + fmtNum(Math.abs(v)) + ' %'; }
    function fmtUsd(v) { return (v >= 0 ? '+' : '−') + fmtNum(Math.abs(v)) + ' $'; }
    function fmtPrice(v) { return fmtNum(v) + ' $'; }

    // XSS protection: escape HTML entities in external data
    function esc(s) {
        if (typeof s !== 'string') return s;
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function setLiveText(attr, text) {
        document.querySelectorAll('[data-live="' + attr + '"]').forEach(function (el) {
            el.textContent = text;
        });
    }

    function setLiveHtml(attr, html) {
        document.querySelectorAll('[data-live="' + attr + '"]').forEach(function (el) {
            el.innerHTML = html;
        });
    }

    function colorClass(v) { return v >= 0 ? 'bull' : 'bear'; }
    function colorVar(v) { return v >= 0 ? 'var(--bull)' : 'var(--bear)'; }

    // ============================================================
    // Tab toggle (cosmetic)
    // ============================================================
    document.querySelectorAll('.tabbar').forEach(function (group) {
        group.querySelectorAll('.tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                group.querySelectorAll('.tab').forEach(function (t) { t.classList.remove('active'); });
                tab.classList.add('active');
            });
        });
    });

    // ============================================================
    // Nav active toggle
    // ============================================================
    document.querySelectorAll('.nav-item').forEach(function (item) {
        item.addEventListener('click', function () {
            document.querySelectorAll('.nav-item').forEach(function (i) { i.classList.remove('active'); });
            item.classList.add('active');
        });
    });

    // ============================================================
    // GLOBAL: fetchJSON + Balance-Polling (auf allen Seiten)
    // ============================================================

    var POLL_LIVE = 3000;     // 3s fuer Live-Daten (Echtzeit-Preise)
    var POLL_CHART = 60000;   // 60s fuer Chart-Daten

    function fetchJSON(url) {
        return fetch(url).then(function (res) {
            if (!res.ok) {
                if (res.status === 401) window.location.href = '/login';
                return null;
            }
            return res.json();
        }).catch(function () { return null; });
    }

    // Globale Live-Daten auf allen Seiten aktualisieren (Balance, Sync, etc.)
    function refreshGlobalData() {
        fetchJSON('/api/live').then(function (data) {
            if (!data) return;
            if (data.balance !== null && data.balance !== undefined) {
                setLiveText('balance', fmtNum(data.balance) + ' $');
                setLiveText('settings_balance', fmtNum(data.balance) + ' $');
            }
            if (data.sync) {
                setLiveText('sync_accuracy_support', fmtNum(data.sync.accuracy, 1) + ' %');
                setLiveText('sync_latency_support', data.sync.avg_latency_ms + ' ms');
            }
        });
    }

    // Auf allen authentifizierten Seiten pollen
    if (window.location.pathname !== '/login' && window.location.pathname !== '/invite') {
        refreshGlobalData();
        setInterval(refreshGlobalData, POLL_LIVE);
    }

    // ============================================================
    // Nur auf /dashboard weitermachen
    // ============================================================
    if (!window.location.pathname.startsWith('/dashboard')) return;

    // ============================================================
    // LIVE DATA POLLING (/api/live)
    // ============================================================

    function refreshLiveData() {
        fetchJSON('/api/live').then(function (data) {
            if (!data) return;

            // --- Kontostand / Portfolio ---
            if (data.balance !== null) {
                setLiveText('balance', fmtNum(data.balance) + ' $');
                setLiveText('portfolio_value', fmtNum(data.balance) + ' $');
            }

            // --- Gesamt P&L (realisiert + unrealisiert) ---
            if (data.total_pnl !== undefined) {
                var pnl = data.total_pnl;
                var el = document.querySelector('[data-live="total_pnl"]');
                if (el) {
                    el.textContent = fmtUsd(pnl);
                    el.style.color = colorVar(pnl);
                }
            }

            // --- Return % seit Start ---
            if (data.total_return_pct !== null && data.total_return_pct !== undefined) {
                var retPct = data.total_return_pct;
                var retEl = document.querySelector('[data-live="total_return_pct"]');
                if (retEl) {
                    retEl.innerHTML = fmtPct(retPct) + ' <span class="sub">seit Start</span>';
                    retEl.style.color = colorVar(retPct);
                    retEl.classList.remove('bull', 'bear');
                    retEl.classList.add(colorClass(retPct));
                }
            }

            // --- Tages-PnL (realisierte Trades heute + unrealisierter P&L) ---
            if (data.starting_balance) {
                var todayRealised = (data.today_pnl !== null && data.today_pnl !== undefined) ? data.today_pnl : 0;
                var todayUnrealised = (data.total_unrealised_pnl !== undefined) ? data.total_unrealised_pnl : 0;
                var todayTotal = todayRealised + todayUnrealised;
                var todayPct = (todayTotal / data.starting_balance) * 100;

                var el2 = document.querySelector('[data-live="today_pnl_pct"]');
                if (el2) {
                    el2.textContent = fmtPct(todayPct);
                    el2.style.color = colorVar(todayPct);
                }

                // Portfolio 1T delta
                var deltaEl = document.querySelector('[data-live="portfolio_1d_delta"]');
                if (deltaEl) {
                    deltaEl.innerHTML =
                        '<svg class="ico" style="width:12px;height:12px;"><use href="#i-trending-' +
                        (todayPct >= 0 ? 'up' : 'down') + '"/></svg>' +
                        fmtPct(todayPct) + ' <span class="sub">1T</span>';
                    deltaEl.classList.remove('bull', 'bear');
                    deltaEl.classList.add(colorClass(todayPct));
                }
                var sparkPath = document.getElementById('sparklinePath');
                if (sparkPath) {
                    sparkPath.setAttribute('stroke', todayPct >= 0 ? '#00C896' : '#FF4D4F');
                }
            }

            // --- Positionen Live-Update ---
            if (data.positions && data.positions.length > 0) {
                data.positions.forEach(function (pos) {
                    var posId = pos.master_position_id;

                    // Aktueller Preis
                    var priceEl = document.querySelector('[data-live-price="' + posId + '"]');
                    if (priceEl && pos.current_price > 0) {
                        var pricePct = pos.price_change_pct;
                        priceEl.innerHTML = fmtPrice(pos.current_price) +
                            ' <span style="color:' + colorVar(pricePct) +
                            ';font-size:11.5px;font-weight:500;margin-left:4px;">' +
                            fmtPct(pricePct) + '</span>';
                    }

                    // Unrealisierter P&L
                    var pnlEl = document.querySelector('[data-live-pnl="' + posId + '"]');
                    if (pnlEl) {
                        var upnl = pos.unrealised_pnl;
                        var upct = pos.pnl_percent;
                        pnlEl.innerHTML =
                            '<div class="pnl-cell num" style="color:' + colorVar(upnl) + ';">' +
                            fmtUsd(upnl) + '</div>' +
                            '<div class="pnl-sub" style="color:' + colorVar(upct) + ';">' +
                            fmtPct(upct) + '</div>';
                    }
                });

                // Open positions count
                var posCount = data.positions.length;
                var posSuffix = posCount !== 1 ? 'en' : '';
                setLiveText('positions_status', 'Live · ' + posCount + ' offene Position' + posSuffix);
                setLiveText('positions_pill', posCount + ' Live-Position' + posSuffix);
                setLiveText('active_count', posCount + ' aktiv');
            }

            // --- Du vs Master vs BTC Comparison ---
            var youPct = data.total_return_pct || 0;
            var masterPct = (data.bot && data.bot.return_pct !== null) ? data.bot.return_pct : youPct;
            var btcPct = data.btc_benchmark_pct;
            var hasBtc = btcPct !== null && btcPct !== undefined;

            // BTC Benchmark anzeigen
            if (hasBtc) {
                setLiveText('btc_benchmark', fmtPct(btcPct));
                var btcEl = document.querySelector('[data-live="btc_benchmark"]');
                if (btcEl) btcEl.style.color = colorVar(btcPct);
            }

            // Farben: gruen wenn besser als BTC, rot wenn schlechter
            var youColor = hasBtc ? (youPct > btcPct ? 'var(--bull)' : 'var(--bear)') : colorVar(youPct);
            var masterColor = hasBtc ? (masterPct > btcPct ? 'var(--bull)' : 'var(--bear)') : colorVar(masterPct);

            var youPctEl = document.querySelector('[data-live="compare_you_pct"]');
            var masterPctEl = document.querySelector('[data-live="compare_master_pct"]');
            if (youPctEl) { youPctEl.textContent = fmtPct(youPct); youPctEl.style.color = youColor; }
            if (masterPctEl) { masterPctEl.textContent = fmtPct(masterPct); masterPctEl.style.color = masterColor; }
            var masterRetEl = document.querySelector('[data-live="master_return_pct"]');
            if (masterRetEl) {
                masterRetEl.textContent = fmtPct(masterPct);
                masterRetEl.style.color = colorVar(masterPct);
            }

            // Balken relativ zum groessten Wert skalieren (groesster = 90% Breite)
            var allPcts = [Math.abs(youPct), Math.abs(masterPct)];
            if (hasBtc) allPcts.push(Math.abs(btcPct));
            var maxAbs = Math.max.apply(null, allPcts.concat([0.01]));

            var youBar = document.getElementById('compareYouBar');
            var masterBar = document.getElementById('compareMasterBar');
            var btcBar = document.getElementById('compareBtcBar');
            if (youBar) youBar.style.width = Math.max(3, Math.abs(youPct) / maxAbs * 90) + '%';
            if (masterBar) masterBar.style.width = Math.max(3, Math.abs(masterPct) / maxAbs * 90) + '%';
            if (btcBar && hasBtc) btcBar.style.width = Math.max(3, Math.abs(btcPct) / maxAbs * 90) + '%';

            // --- Master YTD ---
            if (data.bot && data.bot.ytd_pct !== null && data.bot.ytd_pct !== undefined) {
                var ytdEl = document.querySelector('[data-live="master_ytd_pct"]');
                if (ytdEl) {
                    ytdEl.textContent = fmtPct(data.bot.ytd_pct);
                    ytdEl.className = 'v num ' + colorClass(data.bot.ytd_pct);
                    ytdEl.style.color = colorVar(data.bot.ytd_pct);
                }
            }

            // --- Max Drawdown ---
            if (data.bot && data.bot.max_drawdown_pct !== undefined) {
                var ddVal = data.bot.max_drawdown_pct;
                var ddEl = document.querySelector('[data-live="max_drawdown"]');
                if (ddEl) {
                    ddEl.textContent = '−' + fmtNum(ddVal) + ' %';
                    ddEl.style.color = 'var(--bear)';
                }
            }

            // --- Follower Count ---
            if (data.follower_count !== undefined) {
                setLiveText('follower_count', data.follower_count);
            }

            // --- Customer Stats (Trefferquote, Trades) ---
            if (data.customer) {
                var cs = data.customer;
                var wrColor = cs.win_rate >= 50 ? 'var(--bull)' : 'var(--bear)';
                var posCount2 = data.positions ? data.positions.length : 0;
                setLiveHtml('active_count', posCount2 + ' aktiv');
                var statsFootEl = document.querySelector('[data-live="active_count"]');
                if (statsFootEl && statsFootEl.parentElement) {
                    var parent = statsFootEl.parentElement;
                    parent.innerHTML =
                        '<span class="sub" data-live="active_count">' + posCount2 + ' aktiv</span> · ' +
                        '<span style="color:' + wrColor + ';">' + fmtNum(cs.win_rate, 1) + ' %</span> Trefferquote';
                }
            }

            // --- Sync Metrics ---
            if (data.sync) {
                setLiveText('sync_accuracy', fmtNum(data.sync.accuracy, 1) + ' %');
                setLiveText('sync_latency', data.sync.avg_latency_ms + ' ms Ø Latenz');
                setLiveText('sync_latency_footer', data.sync.avg_latency_ms + ' ms');
                setLiveText('compare_sync', fmtNum(data.sync.accuracy, 1));
            }
        });
    }

    // Sofort starten + Intervall
    refreshLiveData();
    setInterval(refreshLiveData, POLL_LIVE);

    // ============================================================
    // EQUITY CHART (echte Daten von /api/equity)
    // Normalisiert auf Prozent (%), zeigt $ + % an
    // ============================================================

    var chartData = null;
    var currentPeriod = '1M';
    var currentResolution = 'daily';

    var W = 750, PLOT_TOP = 20, PLOT_BOTTOM = 200, PLOT_H = PLOT_BOTTOM - PLOT_TOP;
    var VB_BOTTOM = 220;

    function getX(i, total) { return total <= 1 ? W / 2 : (i / (total - 1)) * W; }
    function getY(val, vMin, vMax) {
        if (vMax === vMin) return PLOT_TOP + PLOT_H / 2;
        return PLOT_TOP + PLOT_H - ((val - vMin) / (vMax - vMin)) * PLOT_H;
    }

    function buildPath(points, vMin, vMax) {
        return points.map(function (p, i) {
            return (i === 0 ? 'M' : 'L') + getX(i, points.length) + ',' + getY(p, vMin, vMax);
        }).join(' ');
    }

    function buildArea(linePath, total) {
        return linePath + ' L' + getX(total - 1, total) + ',' + VB_BOTTOM + ' L0,' + VB_BOTTOM + ' Z';
    }

    // --- Datums-Formatierung pro Zeitraum ---

    var MONTH_NAMES = ['', 'Jan', 'Feb', 'Maer', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
    var WEEKDAY_NAMES = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];

    function formatXLabel(dateStr, period) {
        if (period === '1T') {
            // dateStr = "YYYY-MM-DD HH:00"
            var hourPart = dateStr.split(' ')[1] || '00:00';
            return hourPart.substring(0, 5);
        }
        // dateStr = "YYYY-MM-DD"
        var parts = dateStr.split('-');
        var year = parseInt(parts[0], 10);
        var month = parseInt(parts[1], 10);
        var day = parseInt(parts[2], 10);

        if (period === '1W') {
            var d = new Date(year, month - 1, day);
            return WEEKDAY_NAMES[d.getDay()] + ' ' + day + '.';
        }
        if (period === '1M') {
            return day + '. ' + MONTH_NAMES[month];
        }
        if (period === '3M' || period === 'YTD' || period === 'All') {
            return MONTH_NAMES[month] + ' ' + String(year).slice(2);
        }
        return day + '. ' + MONTH_NAMES[month];
    }

    function formatTooltipDate(dateStr, period) {
        if (period === '1T') {
            var timePart = dateStr.split(' ')[1] || '00:00';
            var datePart = dateStr.split(' ')[0];
            var dp = datePart.split('-');
            return parseInt(dp[2], 10) + '. ' + MONTH_NAMES[parseInt(dp[1], 10)] + ' · ' + timePart.substring(0, 5);
        }
        var parts = dateStr.split('-');
        return parseInt(parts[2], 10) + '. ' + MONTH_NAMES[parseInt(parts[1], 10)] + ' ' + parts[0];
    }

    // --- Luecken fuellen: fehlende Tage/Stunden interpolieren ---

    function fillDateGaps(data, resolution) {
        if (data.length <= 1) return data;
        var filled = [data[0]];
        for (var i = 1; i < data.length; i++) {
            var prev = data[i - 1];
            var curr = data[i];

            if (resolution === 'hourly') {
                // Stundenschritte fuellen
                var prevDate = new Date(prev.date.replace(' ', 'T') + ':00');
                var currDate = new Date(curr.date.replace(' ', 'T') + ':00');
                var stepMs = 3600000; // 1 Stunde
                var t = prevDate.getTime() + stepMs;
                while (t < currDate.getTime()) {
                    var d = new Date(t);
                    var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
                    var dateStr = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':00';
                    filled.push({
                        date: dateStr,
                        youPct: prev.youPct, youPnl: prev.youPnl,
                        masterPct: prev.masterPct, masterPnl: prev.masterPnl,
                    });
                    t += stepMs;
                }
            } else {
                // Tagesschritte fuellen
                var prevParts = prev.date.split('-');
                var currParts = curr.date.split('-');
                var pDate = new Date(parseInt(prevParts[0]), parseInt(prevParts[1]) - 1, parseInt(prevParts[2]));
                var cDate = new Date(parseInt(currParts[0]), parseInt(currParts[1]) - 1, parseInt(currParts[2]));
                var dayMs = 86400000;
                var t2 = pDate.getTime() + dayMs;
                while (t2 < cDate.getTime()) {
                    var d2 = new Date(t2);
                    var pad2 = function(n) { return n < 10 ? '0' + n : '' + n; };
                    var dateStr2 = d2.getFullYear() + '-' + pad2(d2.getMonth() + 1) + '-' + pad2(d2.getDate());
                    filled.push({
                        date: dateStr2,
                        youPct: prev.youPct, youPnl: prev.youPnl,
                        masterPct: prev.masterPct, masterPnl: prev.masterPnl,
                    });
                    t2 += dayMs;
                }
            }
            filled.push(curr);
        }
        return filled;
    }

    function ensureStartPoint(data, period) {
        var now = new Date();
        var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
        var startDate;

        if (period === '1T') {
            startDate = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) + ' 00:00';
        } else {
            var periodDays = { '1W': 7, '1M': 30, '3M': 90, 'YTD': Math.floor((now - new Date(now.getFullYear(), 0, 1)) / 86400000), 'All': 365 };
            var days = periodDays[period] || 30;
            var start = new Date(now.getTime() - days * 86400000);
            startDate = start.getFullYear() + '-' + pad(start.getMonth() + 1) + '-' + pad(start.getDate());
        }

        // Fuer 1T: alte Daten (vor heute) rausfiltern
        if (period === '1T') {
            var todayPrefix = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
            data = data.filter(function (d) { return d.date.indexOf(todayPrefix) === 0; });
        }

        // Startpunkt immer einfuegen (0-Linie am Periodenbeginn)
        var zeroPoint = { date: startDate, youPct: 0, youPnl: 0, masterPct: 0, masterPnl: 0 };
        if (data.length === 0) {
            data.push(zeroPoint);
        } else if (startDate < data[0].date) {
            data.unshift(zeroPoint);
        }

        // Endpunkt "jetzt" hinzufuegen (heutige Linie bis zum Ende)
        var last = data[data.length - 1];
        var endDate;
        if (period === '1T') {
            endDate = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) + ' ' + pad(now.getHours()) + ':00';
        } else {
            endDate = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
        }
        if (endDate > last.date) {
            data.push({
                date: endDate,
                youPct: last.youPct, youPnl: last.youPnl,
                masterPct: last.masterPct, masterPnl: last.masterPnl,
            });
        }

        return data;
    }

    function renderChart(customerCurve, masterCurve) {
        var perfChart = document.getElementById('perfChart');
        if (!perfChart) return;

        // Daten zusammenfuehren (alle Zeitpunkte auf gleiche Achse)
        var allDates = new Set();
        if (customerCurve) customerCurve.forEach(function (d) { allDates.add(d.date); });
        if (masterCurve) masterCurve.forEach(function (d) { allDates.add(d.date); });
        var dates = Array.from(allDates).sort();

        // Maps erstellen (Prozent + Dollar)
        var customerPctMap = {}, customerPnlMap = {};
        if (customerCurve) customerCurve.forEach(function (d) {
            customerPctMap[d.date] = d.cumulative_pct || 0;
            customerPnlMap[d.date] = d.cumulative_pnl || 0;
        });
        var masterPctMap = {}, masterPnlMap = {};
        if (masterCurve) masterCurve.forEach(function (d) {
            masterPctMap[d.date] = d.cumulative_pct || 0;
            masterPnlMap[d.date] = d.cumulative_pnl || 0;
        });

        // Chart-Daten aufbauen
        var data = dates.map(function (date) {
            return {
                date: date,
                youPct: customerPctMap[date] || 0,
                youPnl: customerPnlMap[date] || 0,
                masterPct: masterPctMap[date] || 0,
                masterPnl: masterPnlMap[date] || 0,
            };
        });

        // Start/End-Punkte sicherstellen + Luecken fuellen
        // (auch bei leeren API-Daten werden Null-Punkte erzeugt → flache Linie)
        data = ensureStartPoint(data, currentPeriod);
        data = fillDateGaps(data, currentResolution === 'hourly' ? 'hourly' : 'daily');

        if (data.length === 0) return;

        // Y-Achse laeuft auf Prozent — Min/Max berechnen
        var allPctValues = [];
        data.forEach(function (d) { allPctValues.push(d.youPct, d.masterPct); });
        var yMin = Math.min(0, Math.min.apply(null, allPctValues));
        var yMax = Math.max(0, Math.max.apply(null, allPctValues));
        var padding = (yMax - yMin) * 0.15 || 0.5;
        yMin -= padding;
        yMax += padding;

        // Pfade bauen (auf Prozent-Basis)
        var youPctPoints = data.map(function (d) { return d.youPct; });
        var masterPctPoints = data.map(function (d) { return d.masterPct; });

        var youLineD = buildPath(youPctPoints, yMin, yMax);
        var masterLineD = buildPath(masterPctPoints, yMin, yMax);

        document.getElementById('youLine').setAttribute('d', youLineD);
        document.getElementById('youArea').setAttribute('d', buildArea(youLineD, data.length));
        document.getElementById('masterLine').setAttribute('d', masterLineD);
        document.getElementById('masterArea').setAttribute('d', buildArea(masterLineD, data.length));

        // Grid + Y-Achse dynamisch (zeigt %)
        var gridG = document.getElementById('chartGrid');
        var yAxisG = document.getElementById('chartYAxis');
        gridG.innerHTML = '';
        yAxisG.innerHTML = '';

        // Intelligente Tick-Berechnung: Schrittgroesse so waehlen,
        // dass Labels immer unterschiedlich und sinnvoll lesbar sind
        var range = yMax - yMin;
        var rawStep = range / 4;

        // Passende Schrittgroesse finden (1, 2, 5, 10, 20, 50 ... oder 0.1, 0.05, 0.01, ...)
        var mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
        var residual = rawStep / mag;
        var niceStep;
        if (residual <= 1.5) niceStep = 1 * mag;
        else if (residual <= 3.5) niceStep = 2 * mag;
        else if (residual <= 7.5) niceStep = 5 * mag;
        else niceStep = 10 * mag;

        // Dezimalstellen bestimmen (basierend auf Schrittgroesse)
        var decimals;
        if (niceStep >= 1) decimals = 0;
        else if (niceStep >= 0.1) decimals = 1;
        else if (niceStep >= 0.01) decimals = 2;
        else if (niceStep >= 0.001) decimals = 3;
        else decimals = 4;

        // Ticks generieren: vom niedrigsten zum hoechsten "nice" Wert
        var tickStart = Math.ceil(yMin / niceStep) * niceStep;
        var ticks = [];
        for (var tv = tickStart; tv <= yMax + niceStep * 0.01; tv += niceStep) {
            ticks.push(tv);
        }
        // Maximal 6 Ticks, damit es nicht zu eng wird
        if (ticks.length > 6) {
            var skip = Math.ceil(ticks.length / 5);
            ticks = ticks.filter(function (_, idx) { return idx % skip === 0; });
        }

        ticks.forEach(function (val) {
            var yPos = getY(val, yMin, yMax);
            if (yPos < PLOT_TOP - 5 || yPos > PLOT_BOTTOM + 5) return;

            var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', '0'); line.setAttribute('y1', yPos);
            line.setAttribute('x2', W); line.setAttribute('y2', yPos);
            gridG.appendChild(line);

            var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', W + 7); text.setAttribute('y', yPos + 4);
            var label = (val >= 0 ? '+' : '') + fmtNum(val, decimals) + ' %';
            text.textContent = label;
            yAxisG.appendChild(text);
        });

        // X-Achse — Labels passend zum Zeitraum
        var xAxisG = document.getElementById('chartXAxis');
        xAxisG.innerHTML = '';

        // Anzahl Labels je nach Datenmenge
        var labelCount = Math.min(data.length, currentPeriod === '1T' ? 6 : 4);
        var xIndices = [];
        for (var li = 0; li < labelCount; li++) {
            xIndices.push(Math.round(li * (data.length - 1) / (labelCount - 1 || 1)));
        }
        // Duplikate entfernen
        xIndices = xIndices.filter(function (v, i, a) { return a.indexOf(v) === i; });

        xIndices.forEach(function (idx) {
            if (idx >= data.length) return;
            var text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', getX(idx, data.length));
            text.setAttribute('y', 252);
            var isFirst = idx === 0;
            var isLast = idx === data.length - 1;
            text.setAttribute('text-anchor', isFirst ? 'start' : (isLast ? 'end' : 'middle'));
            text.textContent = isLast ? 'Jetzt' : formatXLabel(data[idx].date, currentPeriod);
            xAxisG.appendChild(text);
        });

        // Chart-Stats aktualisieren — Dollar + Prozent
        var lastYou = data[data.length - 1];
        var lastMaster = data[data.length - 1];
        setLiveHtml('chart_you_value',
            fmtUsd(lastYou.youPnl) +
            ' <span class="delta ' + colorClass(lastYou.youPct) + '">' +
            fmtPct(lastYou.youPct) + '</span>');
        setLiveHtml('chart_master_pct',
            fmtUsd(lastMaster.masterPnl) +
            ' <span class="delta ' + colorClass(lastMaster.masterPct) + '" style="font-size:11px;margin-left:4px;">' +
            fmtPct(lastMaster.masterPct) + '</span>');

        // Store data for hover
        chartData = data;
        chartYMin = yMin;
        chartYMax = yMax;

        // Dots positionieren
        setChartIdle();
    }

    var chartYMin = 0, chartYMax = 30;

    function renderMasterMiniChart(points) {
        if (!points || points.length < 2) return;
        var miniW = 240, miniH = 110, padTop = 10, padBot = 10;
        var plotH = miniH - padTop - padBot;
        var mn = Math.min.apply(null, points);
        var mx = Math.max.apply(null, points);
        if (mx === mn) { mn -= 1; mx += 1; }

        var lineD = points.map(function (p, i) {
            var x = (i / (points.length - 1)) * miniW;
            var y = padTop + plotH - ((p - mn) / (mx - mn)) * plotH;
            return (i === 0 ? 'M' : 'L') + x + ',' + y;
        }).join(' ');

        var areaD = lineD + ' L' + miniW + ',' + miniH + ' L0,' + miniH + ' Z';

        var miniLine = document.getElementById('masterMiniLine');
        var miniArea = document.getElementById('masterMiniArea');
        if (miniLine) miniLine.setAttribute('d', lineD);
        if (miniArea) miniArea.setAttribute('d', areaD);
    }

    // ============================================================
    // CHART HOVER INTERACTIVITY
    // ============================================================

    var youDot = document.getElementById('youDot');
    var youDotHalo = document.getElementById('youDotHalo');
    var masterDot = document.getElementById('masterDot');
    var crosshair = document.getElementById('crosshair');
    var tooltip = document.getElementById('perfTooltip');
    var hoverRect = document.getElementById('hoverRect');
    var wrap = document.getElementById('perfChartWrap');
    var svg = document.getElementById('perfChart');

    function setChartIdle() {
        if (!chartData || chartData.length === 0) return;
        var endIdx = chartData.length - 1;
        var endX = getX(endIdx, chartData.length);
        var endY = getY(chartData[endIdx].youPct, chartYMin, chartYMax);
        if (youDot) { youDot.setAttribute('cx', endX); youDot.setAttribute('cy', endY); }
        if (youDotHalo) { youDotHalo.setAttribute('cx', endX); youDotHalo.setAttribute('cy', endY); }
        if (masterDot) masterDot.setAttribute('opacity', '0');
        if (crosshair) crosshair.setAttribute('opacity', '0');
        if (tooltip) tooltip.style.display = 'none';
    }

    if (hoverRect) {
        hoverRect.addEventListener('mousemove', function (e) {
            if (!chartData || chartData.length === 0) return;
            var rect = svg.getBoundingClientRect();
            var vbX = ((e.clientX - rect.left) / rect.width) * 800;
            var clampedX = Math.max(0, Math.min(W, vbX));
            var endIdx = chartData.length - 1;
            var i = Math.max(0, Math.min(endIdx, Math.round(clampedX / W * endIdx)));
            var d = chartData[i];
            var x = getX(i, chartData.length);
            var yY = getY(d.youPct, chartYMin, chartYMax);
            var mY = getY(d.masterPct, chartYMin, chartYMax);

            crosshair.setAttribute('x1', x); crosshair.setAttribute('x2', x);
            crosshair.setAttribute('opacity', '1');
            youDot.setAttribute('cx', x); youDot.setAttribute('cy', yY);
            youDotHalo.setAttribute('cx', x); youDotHalo.setAttribute('cy', yY);
            masterDot.setAttribute('cx', x); masterDot.setAttribute('cy', mY);
            masterDot.setAttribute('opacity', '1');

            var ttDate = tooltip.querySelector('.tt-date');
            var ttYou = tooltip.querySelector('.you-val');
            var ttMaster = tooltip.querySelector('.master-val');
            var ttEquity = tooltip.querySelector('.you-equity');

            ttDate.textContent = formatTooltipDate(d.date, currentPeriod);
            ttYou.textContent = fmtUsd(d.youPnl) + '  ' + fmtPct(d.youPct);
            ttMaster.textContent = fmtUsd(d.masterPnl) + '  ' + fmtPct(d.masterPct);
            if (ttEquity) ttEquity.textContent = fmtPct(d.youPct);

            var wrapRect = wrap.getBoundingClientRect();
            var ttX = (x / 800) * wrapRect.width;
            var ttY = (yY / 280) * wrapRect.height;

            // Tooltip-Position clampen (nicht abschneiden lassen)
            var ttWidth = tooltip.offsetWidth || 180;
            var minX = ttWidth / 2 + 4;
            var maxX = wrapRect.width - ttWidth / 2 - 4;
            ttX = Math.max(minX, Math.min(maxX, ttX));
            if (ttY < 80) ttY = 80; // Nicht ueber den Chart hinaus

            tooltip.style.left = ttX + 'px';
            tooltip.style.top = ttY + 'px';
            tooltip.style.display = 'block';
        });

        hoverRect.addEventListener('mouseleave', setChartIdle);
    }

    // ============================================================
    // CHART PERIOD SWITCHING
    // ============================================================

    var chartTabbar = document.getElementById('chartTabbar');
    if (chartTabbar) {
        chartTabbar.addEventListener('click', function (e) {
            var tab = e.target.closest('.tab');
            if (!tab) return;
            var period = tab.getAttribute('data-period');
            if (period) {
                currentPeriod = period;
                loadChartData(period);
            }
        });
    }

    function loadChartData(period) {
        fetchJSON('/api/equity?period=' + period).then(function (data) {
            if (!data) return;
            currentResolution = data.resolution || 'daily';
            renderChart(data.customer, data.master);
        });
    }

    // Chart initial laden
    loadChartData(currentPeriod);
    setInterval(function () { loadChartData(currentPeriod); }, POLL_CHART);

    // ============================================================
    // MASTER MINI CHART (Gesamtperformance seit Start)
    // ============================================================

    function loadMasterMiniChart() {
        fetchJSON('/api/equity?period=All').then(function (data) {
            if (!data || !data.master || data.master.length === 0) return;
            var points = data.master.map(function (d) { return d.cumulative_pct || 0; });
            // Start bei 0 einfuegen falls nicht vorhanden
            if (points.length === 1) points.unshift(0);
            renderMasterMiniChart(points);
        });
    }

    loadMasterMiniChart();
    setInterval(loadMasterMiniChart, POLL_CHART);

    // ============================================================
    // PORTFOLIO SPARKLINE (letzte 7 Tage)
    // ============================================================

    function updateSparkline() {
        fetchJSON('/api/equity?period=1W').then(function (data) {
            if (!data || !data.customer || data.customer.length < 2) return;
            var points = data.customer.map(function (d) { return d.cumulative_pnl; });
            var mn = Math.min.apply(null, points);
            var mx = Math.max.apply(null, points);
            if (mx === mn) { mn -= 1; mx += 1; }

            var d = points.map(function (p, i) {
                var x = (i / (points.length - 1)) * 68;
                var y = 22 - ((p - mn) / (mx - mn)) * 20;
                return (i === 0 ? 'M' : 'L') + x + ',' + y;
            }).join(' ');

            var sparkline = document.getElementById('sparklinePath');
            if (sparkline) {
                sparkline.setAttribute('d', d);
                // Farbe basierend auf Trend
                var trend = points[points.length - 1] - points[0];
                sparkline.setAttribute('stroke', trend >= 0 ? '#00C896' : '#FF4757');
            }
        });
    }

    updateSparkline();

    // ============================================================
    // LIVE FEED POLLING (/api/feed)
    // ============================================================

    function refreshFeed() {
        fetchJSON('/api/feed').then(function (data) {
            if (!data || !data.events || data.events.length === 0) return;
            var feedEl = document.querySelector('.feed-card .feed');
            if (!feedEl) return;

            var html = data.events.map(function (ev) {
                var isBull = ev.action === 'OPEN' || ev.action === 'SCALE_IN' || ev.pnl >= 0;
                var isBear = ev.action === 'CLOSE' && ev.pnl < 0;
                var cls = isBear ? 'bear' : 'bull';
                var icon = isBear ? 'i-arrow-down-right' : 'i-arrow-up-right';

                var pnlStr = '';
                if (ev.action === 'CLOSE' || ev.action === 'SCALE_OUT') {
                    pnlStr = ' · <span class="' + cls + '">' +
                        (ev.pnl >= 0 ? '+' : '') + fmtNum(ev.pnl) + ' $</span>';
                }

                var timeStr = ev.created_at ? ev.created_at.substring(0, 16).replace('T', ' ') : '';

                return '<div class="feed-item">' +
                    '<div class="feed-ico ' + cls + '">' +
                    '<svg class="ico"><use href="#' + icon + '"/></svg></div>' +
                    '<div class="feed-body">' +
                    '<div class="feed-title"><b>' + esc(ev.label) + '</b> ' +
                    '<span class="pair">' + esc(ev.symbol) + '</span>' + pnlStr + '</div>' +
                    '<div class="feed-meta">' + esc(ev.side) +
                    (ev.price > 0 ? ' · ' + fmtNum(ev.price) + ' $' : '') +
                    ' <span class="sep">·</span> ' + esc(timeStr) + '</div>' +
                    '</div></div>';
            }).join('');

            feedEl.innerHTML = html;
        });
    }

    refreshFeed();
    setInterval(refreshFeed, POLL_LIVE);

    // ============================================================
    // LETZTE TRADES POLLING (/api/recent-trades)
    // ============================================================

    function refreshRecentTrades() {
        fetchJSON('/api/recent-trades').then(function (data) {
            if (!data || !data.trades) return;
            var listEl = document.querySelector('.activity-card .activity-list');
            if (!listEl) return;

            if (data.trades.length === 0) {
                listEl.innerHTML = '<div style="padding:40px 24px;text-align:center;color:var(--tx-3);font-size:13px;">Noch keine abgeschlossenen Trades.</div>';
                return;
            }

            var html = data.trades.map(function (t) {
                var cls = t.pnl >= 0 ? 'bull' : 'bear';
                var icon = t.pnl >= 0 ? 'i-arrow-up-right' : 'i-arrow-down-right';

                return '<div class="activity-item">' +
                    '<div class="act-ico ' + cls + '">' +
                    '<svg class="ico"><use href="#' + icon + '"/></svg></div>' +
                    '<div class="act-body">' +
                    '<div class="act-title"><b>' + esc(t.symbol) + '</b> · ' + esc(t.side) + '</div>' +
                    '<div class="act-meta">Geschlossen ' + esc(t.closed_at) + ' · ' + esc(t.duration) + '</div>' +
                    '</div>' +
                    '<div>' +
                    '<div class="act-value ' + cls + ' num">' +
                    (t.pnl >= 0 ? '+' : '') + fmtNum(t.pnl) + ' $</div>' +
                    '<div class="act-meta ' + cls + '">' +
                    (t.pnl_pct >= 0 ? '+' : '') + fmtNum(t.pnl_pct) + ' %</div>' +
                    '</div></div>';
            }).join('');

            listEl.innerHTML = html;
        });
    }

    refreshRecentTrades();
    setInterval(refreshRecentTrades, POLL_LIVE);

})();
