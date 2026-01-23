export async function fetchPoints() {
  const res = await fetch('/points');
  const points = await res.json();
  const tbody = document.getElementById('points-table');
  tbody.innerHTML = '';
  points.forEach(p => {
    tbody.innerHTML += `
      <tr>
        <td><input type="checkbox" value="${p.id}"></td>
        <td>${p.name}</td>
        <td>${p.owner}</td>
        <td>${p.idTg ?? ''}</td>
      </tr>`;
  });
}

document.getElementById('points-form').onsubmit = async e => {
  e.preventDefault();
  const name = document.getElementById('point-name').value.trim();
  const owner = document.getElementById('point-owner').value.trim();
  const idTg = document.getElementById('point-idtg').value.trim();

  if (!name || !owner || !idTg) return alert('Пожалуйста, заполните все поля.');

  await fetch('/points', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, owner, idTg })
  });

  e.target.reset();
  fetchPoints();
};

export function toggleAllPoints(cb) {
  document.querySelectorAll('#points-table input[type=checkbox]').forEach(c => c.checked = cb.checked);
}

export async function deleteSelectedPoints() {
  const ids = Array.from(document.querySelectorAll('#points-table input[type=checkbox]:checked')).map(c => parseInt(c.value));
  if (!ids.length) return;
  await fetch('/points/', { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ids) });
  fetchPoints();
}
