/**
 * _design-toggle.js — live A/B testing for MP/EP toggle design options.
 *
 * Usage: load via <script> tag in index.html, then visit:
 *   /#/2026-07-18/mp?toggle=1  →  Desktop dropdown, mobile pills
 *   /#/2026-07-18/mp?toggle=2  →  Centered text links
 *   /#/2026-07-18/mp?toggle=3  →  Underline tabs
 *   /#/2026-07-18/mp?toggle=4  →  Integrated heading switcher
 *   (no ?toggle)               →  Current pill controls (unchanged)
 */

(function () {
  const opt = parseInt(new URLSearchParams(location.hash.split('?')[1] || '').get('toggle'));
  if (!opt || opt < 1 || opt > 4) return;

  const styleEl = document.createElement('style');
  styleEl.id = 'design-toggle-styles';
  document.head.appendChild(styleEl);

  let sheet = '';

  switch (opt) {
    case 2: {
      // Centered text links
      sheet += `
        #day-office-controls .day-ctrl-group:first-child { display: none; }
      `;
      break;
    }
    case 3: {
      // Underline tabs — strip pill container, style as tab row
      sheet += `
        #day-office-controls .day-ctrl-seg {
          background: none; border: none; border-radius: 0; padding: 0;
          justify-content: center; gap: 1.5rem;
        }
        #day-office-controls .day-ctrl-btn {
          flex: none; background: none; padding: 0.25rem 0 0.35rem; border-radius: 0;
          border-bottom: 2px solid transparent; box-shadow: none;
          font-size: 0.7rem; letter-spacing: 0.16em; text-transform: uppercase;
        }
        #day-office-controls .day-ctrl-btn.is-active {
          background: none; color: var(--color-accent);
          border-bottom-color: var(--color-accent); box-shadow: none;
        }
        #day-office-controls .day-ctrl-btn:hover { color: var(--color-text); }
      `;
      break;
    }
    case 4: {
      // Integrated heading switcher — hide controls, make heading clickable
      sheet += `
        #day-office-controls { display: none; }
        #day-office-name { cursor: pointer; }
        #day-office-name::after { content: ' \\25BE'; font-size: 0.8em; opacity: 0.5; }
        #day-office-name:hover { opacity: 0.85; }
      `;
      break;
    }
  }

  if (sheet) styleEl.textContent = sheet;

  function apply() {
    const ctrlEl = document.getElementById('day-office-controls');
    if (!ctrlEl) return;

    switch (opt) {
      case 1: {
        // Desktop dropdown / mobile pills
        const existing = document.getElementById('office-dropdown-wrap');
        if (existing) existing.remove();

        const wrap = document.createElement('div');
        wrap.className = 'day-ctrl-group';
        wrap.id = 'office-dropdown-wrap';
        const sel = document.createElement('select');
        sel.className = 'office-dropdown';
        sel.innerHTML =
          '<option value="mp">Morning Prayer</option>' +
          '<option value="ep">Evening Prayer</option>';
        sel.value = document.getElementById('day-office-name').textContent.includes('Evening') ? 'ep' : 'mp';
        sel.addEventListener('change', () => {
          location.hash = location.hash.replace(/\/mp/, '/__').replace(/\/ep/, '\/mp').replace(/\/__/, '/ep');
        });
        wrap.appendChild(sel);
        ctrlEl.classList.add('toggle-opt-1');
        ctrlEl.appendChild(wrap);
        break;
      }
      case 2: {
        // Text links
        const mpEl = document.getElementById('day-office-name');
        if (!mpEl) return;
        const isEP = mpEl.textContent.includes('Evening');
        const mpLink = location.hash.includes('/mp');
        const epLink = location.hash.includes('/ep');
        const mpHash = location.hash.replace(/\/ep/, '/mp');
        const epHash = location.hash.replace(/\/mp/, '/ep');
        const existing2 = document.getElementById('office-links-wrap');
        if (existing2) existing2.remove();

        const wrap = document.createElement('div');
        wrap.id = 'office-links-wrap';
        wrap.className = 'office-links';
        const mid = document.createElement('span');
        mid.className = 'office-links-sep';
        mid.textContent = '·';
        const aMP = document.createElement('a');
        aMP.href = mpHash;
        aMP.textContent = 'Morning Prayer';
        aMP.className = 'office-link' + (isEP ? '' : ' office-link--active');
        const aEP = document.createElement('a');
        aEP.href = epHash;
        aEP.textContent = 'Evening Prayer';
        aEP.className = 'office-link' + (isEP ? ' office-link--active' : '');
        wrap.appendChild(aMP);
        wrap.appendChild(mid);
        wrap.appendChild(aEP);
        wrap.querySelectorAll('a').forEach(a => {
          a.addEventListener('click', e => {
            e.preventDefault();
            location.hash = a.href.split('#')[1];
          });
        });
        ctrlEl.parentNode.insertBefore(wrap, ctrlEl);
        break;
      }
      case 4: {
        // Integrated heading — clicking heading switches office
        const h4El = document.getElementById('day-office-name');
        if (!h4El || h4El.dataset.toggleWired) return;
        h4El.dataset.toggleWired = '1';
        h4El.addEventListener('click', () => {
          const alt = h4El.textContent.includes('Morning') ? 'ep' : 'mp';
          location.hash = location.hash.replace(/\/mp/, '/__').replace(/\/ep/, '\/mp').replace(/\/__/, '/ep');
        });
        break;
      }
    }
  }

  // Apply on load + after each office switch (DOM changes)
  const observer = new MutationObserver(() => apply());
  observer.observe(document.getElementById('day-office-controls'), { childList: true, subtree: true });
  apply();
})();
