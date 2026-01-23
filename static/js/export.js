import { setCookie, getCookie } from './utils.js';

const exportButtons = document.querySelectorAll('.export-btn');
let selectedExport = null;

function markAsSent(tableId) {
  const btn = document.getElementById(tableId);
  if (btn) btn.style.background = '#4caf50';
  const expiry = new Date();
  expiry.setDate(expiry.getDate() + ((6 - expiry.getDay() + 7) % 7));
  setCookie(`sent_${tableId}`, '1', expiry);
}

function updateExportButtonColors() {
  exportButtons.forEach(btn => {
    if (getCookie(`sent_${btn.id}`)) {
      btn.style.background = '#4caf50';
      btn.classList.remove('active');
    } else if (btn.id === selectedExport) {
      btn.style.background = '#ff9800';
      btn.classList.add('active');
    } else {
      btn.style.background = '#4a90e2';
      btn.classList.remove('active');
    }
  });
}

exportButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    selectedExport = btn.id;
    updateExportButtonColors();
    downloadExcel(`/export/${btn.id.replace('export-','')}`, btn.id);
  });
});

updateExportButtonColors();

async function downloadExcel(endpoint, defaultName) {
  try {
    const res = await fetch(endpoint);
    if (!res.ok) throw new Error('Ошибка при генерации Excel');
    const blob = await res.blob();
    const data = await blob.arrayBuffer();
    const workbook = XLSX.read(data, { type: 'array' });
    const sheetName = workbook.SheetNames[0];
    const worksheet = workbook.Sheets[sheetName];
    const rows = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
    renderExcelPreview(rows);
  } catch (err) {
    console.error(err);
    alert(`Не удалось отобразить файл: ${defaultName}`);
  }
}

function renderExcelPreview(rows) {
  const container = document.getElementById('export-preview');
  if (!rows.length) {
    container.innerHTML = '<p>Файл пуст или не удалось прочитать данные.</p>';
    return;
  }
  const maxCols = Math.max(...rows.map(r => r.length));
  let html = '<table><thead><tr>';
  for (let i = 0; i < maxCols; i++) html += `<th>${rows[0][i] ?? ''}</th>`;
  html += '</tr></thead><tbody>';
  for (let i = 1; i < rows.length; i++) {
    html += '<tr>';
    for (let j = 0; j < maxCols; j++) {
      html += `<td contenteditable="true">${rows[i][j] ?? ''}</td>`;
    }
    html += '</tr>';
  }
  html += '</tbody></table>';
  container.innerHTML = html;
}

// Поставщики
const sendSupplierBtn = document.getElementById('send-supplier');
const supplierList = document.getElementById('supplier-list');
const confirmSendBtn = document.getElementById('confirm-send');
const supplierSelect = document.getElementById('supplier-select');

sendSupplierBtn.addEventListener('click', () => {
  supplierList.style.display = supplierList.style.display === 'none' ? 'block' : 'none';
});

confirmSendBtn.addEventListener('click', () => {
  const supplier = supplierSelect.value;
  if (!supplier) return alert('Пожалуйста, выберите поставщика.');
  if (!selectedExport) return alert('Выберите таблицу для отправки.');
  if (confirm(`Отправить таблицу ${selectedExport} поставщику №${supplier}?`)) {
    markAsSent(selectedExport);
    updateExportButtonColors();
    supplierList.style.display = 'none';
    supplierSelect.value = '';
    alert(`Данные успешно отправлены поставщику №${supplier}!`);
  }
});
