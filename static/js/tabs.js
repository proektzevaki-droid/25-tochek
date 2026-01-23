export function switchTab(tab) {
  document.getElementById('orders-section').style.display = tab === 'orders' ? 'block' : 'none';
  document.getElementById('points-section').style.display = tab === 'points' ? 'block' : 'none';
  document.getElementById('export-section').style.display = tab === 'export' ? 'block' : 'none';
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
}
