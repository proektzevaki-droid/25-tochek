import { exportToExcel } from './export.js';

let currentFilter = 'all';
let selectedOrderId = null;

export async function fetchOrders() {
  try {
    const res = await fetch(`/orders?status=${currentFilter}`);
    if (!res.ok) throw new Error('Ошибка загрузки заказов');
    const orders = await res.json();
    const tbody = document.getElementById('orders-table');
    tbody.innerHTML = '';

    if (!orders.length) {
      tbody.innerHTML = `<tr><td colspan="5">Нет заказов</td></tr>`;
      return;
    }

    for (const o of orders) {
      const statusClass = o.status === 'new' ? 'status-new' : o.status === 'confirmed' ? 'status-confirmed' : 'status-rejected';
      const selectedClass = o.id === selectedOrderId ? 'selected' : '';
      const row = document.createElement('tr');
      row.className = `${statusClass} ${selectedClass}`;
      row.innerHTML = `
        <td>${o.id}</td>
        <td>${o.point ? o.point.name : ''}</td>
        <td>${new Date(o.created_at).toLocaleString()}</td>
        <td>${o.status}</td>
        <td><button data-id="${o.id}" class="open-btn">Открыть</button></td>`;
      tbody.appendChild(row);
    }

    document.querySelectorAll('.open-btn').forEach(btn => {
      btn.onclick = () => showOrder(btn.dataset.id);
    });
  } catch (err) { console.error(err); }
}

function setFilter(status) {
  currentFilter = status;
  document.querySelectorAll('.filter-buttons button').forEach(b => b.classList.remove('active'));
  document.querySelector(`button[data-filter="${status}"]`).classList.add('active');
  fetchOrders();
}

document.querySelectorAll('.filter-buttons button').forEach(btn => {
  btn.addEventListener('click', () => setFilter(btn.dataset.filter));
});

async function showOrder(id) {
  selectedOrderId = parseInt(id);
  fetchOrders();
  const res = await fetch(`/orders/${id}`);
  if (!res.ok) return;
  const o = await res.json();

  let html = `
    <h3>Заказ №${o.id}</h3>
    <p><b>Точка:</b> ${o.point ? o.point.name : ''}</p>
    <p><b>Дата:</b> ${new Date(o.created_at).toLocaleString()}</p>
    <p><b>Имя TG:</b> ${o.tg_name}</p>
    <p><b>Username TG:</b> ${o.tg_username}</p>
    <p><b>Статус:</b> ${o.status}</p>
    <h4>Продукты:</h4>
    <table><thead><tr><th>Название</th><th>Кол-во</th></tr></thead><tbody>`;

  o.items.forEach(i => html += `<tr><td>${i.name}</td><td>${i.count}</td></tr>`);
  html += '</tbody></table>';
  html += `<div class="action-buttons"><button class="excel" id="export-btn">Сохранить в Excel</button></div>`;

  if (o.status === 'new') {
    html += `<div class="action-buttons">
      <button class="accept" id="accept-btn">Принять</button>
      <button class="reject" id="reject-btn">Отклонить</button>
    </div>`;
  }

  const details = document.getElementById('order-details');
  details.innerHTML = html;

  document.getElementById('export-btn').onclick = () => exportToExcel(o.id);
  if (o.status === 'new') {
    document.getElementById('accept-btn').onclick = () => confirmAction(o.id, 'confirmed');
    document.getElementById('reject-btn').onclick = () => confirmAction(o.id, 'rejected');
  }
}

async function confirmAction(orderId, newStatus) {
  const actionText = newStatus === 'confirmed' ? 'принять' : 'отклонить';
  if (confirm(`Вы уверены, что хотите ${actionText} этот заказ?`)) {
    const res = await fetch(`/orders/${orderId}/status?status=${newStatus}`, { method: 'PATCH' });
    if (res.ok) showOrder(orderId);
    else alert('Ошибка при обновлении статуса');
  }
}

export async function exportToExcel(orderId) {
  const res = await fetch(`/orders/${orderId}/export`);
  if (!res.ok) return alert("Ошибка при экспорте в Excel");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `order_${orderId}.xlsx`;
  a.click();
  window.URL.revokeObjectURL(url);
}
