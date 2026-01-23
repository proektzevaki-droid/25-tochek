import { switchTab } from './tabs.js';
import { fetchOrders } from './orders.js';
import { fetchPoints } from './points.js';
import './export.js'; // содержит свои обработчики

// ==== Tabs ====
document.getElementById('tab-orders').onclick = () => switchTab('orders');
document.getElementById('tab-points').onclick = () => switchTab('points');
document.getElementById('tab-export').onclick = () => switchTab('export');

// ==== Автообновление ====
setInterval(fetchOrders, 5000);
setInterval(fetchPoints, 10000);
fetchOrders();
fetchPoints();
