const API_URL = 'http://localhost:8000';

let LAST_RESULT = null;

document.getElementById('profile-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const profile = {
    age: parseInt(document.getElementById('age').value),
    gender: document.getElementById('gender').value,
    height_cm: parseFloat(document.getElementById('height').value),
    weight_kg: parseFloat(document.getElementById('weight').value),
    activity: document.getElementById('activity').value,
    goal: document.getElementById('goal').value,
    diet_type: document.getElementById('diet_type').value,
    days: parseInt(document.getElementById('days').value),
    exclude: document.getElementById('exclude').value || ""
  };

  document.getElementById('form-card').style.display = 'none';
  document.getElementById('loading').style.display = 'block';
  document.getElementById('results').style.display = 'none';

  try {
    const response = await fetch(`${API_URL}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile)
    });
    const data = await response.json();

    if (data.success) {
      displayResults(data);
    } else {
      alert('Error: ' + data.error);
      resetForm();
    }
  } catch (err) {
    alert('Failed to generate plan. Make sure the backend is running!');
    console.error(err);
    resetForm();
  }
});

function displayResults(data) {
  LAST_RESULT = data; // ⬅ keep it for Save/Print

  document.getElementById('loading').style.display = 'none';
  document.getElementById('results').style.display = 'block';

  // hook up buttons (safe to rebind each render)
  const btnPrint = document.getElementById('btn-print');
  const btnSaveJSON = document.getElementById('btn-save-json');

  if (btnPrint) {
    btnPrint.onclick = () => {
      // Use the browser dialog; users can pick their printer or "Save as PDF"
      window.print();
    };
  }

  if (btnSaveJSON) {
    btnSaveJSON.onclick = () => {
      if (!LAST_RESULT) return;
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      const filename = `dietplan_${stamp}.json`;
      const blob = new Blob([JSON.stringify(LAST_RESULT, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    };
  }

  // Notice
  const noticeEl = document.getElementById('notice');
  const noticeText = data?.plan?.notice;
  if (noticeText && typeof noticeText === 'string' && noticeText.trim()) {
    noticeEl.textContent = noticeText.trim();
    noticeEl.style.display = 'block';
  } else {
    noticeEl.style.display = 'none';
  }

  // Targets
  const t = data.targets;
  const targetsHTML = `
    <h3>Daily Targets</h3>
    <div class="target-row"><span>Calories:</span><strong>${t.calories} kcal</strong></div>
    <div class="target-row"><span>Protein:</span><strong>${t.macros.protein_g}g</strong></div>
    <div class="target-row"><span>Carbs:</span><strong>${t.macros.carbs_g}g</strong></div>
    <div class="target-row"><span>Fats:</span><strong>${t.macros.fats_g}g</strong></div>
  `;
  document.getElementById('targets').innerHTML = targetsHTML;

  // Helpers for details/totals
  const plan = data.plan;
  const catalog = plan.catalog || {};
  const dayTotals = plan.day_totals || [];

  function detailsFor(name) {
    return catalog[(name || '').toLowerCase()] || null;
  }
  function pct(val, target) {
    if (!target || target <= 0) return 0;
    return Math.min(100, Math.round((val / target) * 100));
  }

  // Days
  let planHTML = '';
  plan.days.forEach((day, idx) => {
    const totals = dayTotals[idx] || {calories:0, protein:0, carbs:0, fats:0};
    const calPct = pct(totals.calories, t.calories);

    planHTML += `
      <div class="day-card">
        <h3>Day ${day.day}</h3>

        <div class="day-summary">
          Total: <strong>${totals.calories} kcal</strong> • 
          P: <strong>${totals.protein}g</strong> • 
          C: <strong>${totals.carbs}g</strong> • 
          F: <strong>${totals.fats}g</strong>
          <div class="progress"><div style="width:${calPct}%"></div></div>
        </div>

        ${day.meals.map(meal => {
          const d = detailsFor(meal.name);
          const p = d?.protein ?? 0, c = d?.carbs ?? 0, f = d?.fats ?? 0;
          const tags = (d?.tags || []).slice(0, 4);
          const diet = (d?.diet || []).slice(0, 2);
          const cuisine = d?.cuisine ? [d.cuisine] : [];

          const badgeHTML = [...diet, ...cuisine, ...tags]
            .map(x => `<span class="badge">${x}</span>`).join('');

          return `
            <div class="meal">
              <div class="meal-header">
                <span class="meal-type">${meal.type}</span>
                <span class="meal-calories">${meal.calories} kcal</span>
              </div>
              <div class="meal-name">${meal.name}</div>
              <div class="macros">
                <span>P: ${p}g</span>
                <span>C: ${c}g</span>
                <span>F: ${f}g</span>
              </div>
              <div class="badges">${badgeHTML}</div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  });

  // Optional weekly summary
  if (plan.summary) {
    planHTML += `
      <div class="day-card">
        <h3>Plan Summary</h3>
        <div>Average Calories: <strong>${plan.summary.avg_calories} kcal</strong></div>
        <div>Average Protein: <strong>${plan.summary.avg_protein} g</strong></div>
      </div>
    `;
  }

  document.getElementById('plan').innerHTML = planHTML;
}

function resetForm() {
  document.getElementById('form-card').style.display = 'block';
  document.getElementById('loading').style.display = 'none';
  document.getElementById('results').style.display = 'none';
}
