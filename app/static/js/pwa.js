/**
 * Mall Billing System — PWA Controller
 * ====================================
 * Handles IndexedDB for offline transactions and 
 * coordinates with the Service Worker for background sync.
 */

const DB_NAME = 'MallBillingDB';
const DB_VERSION = 1;
const STORE_NAME = 'offlineSales';

let db;

// ── Initialize IndexedDB ───────────────────────────────────────────────
const request = indexedDB.open(DB_NAME, DB_VERSION);

request.onupgradeneeded = (event) => {
    db = event.target.result;
    if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
        console.log('IndexedDB: Object store created.');
    }
};

request.onsuccess = (event) => {
    db = event.target.result;
    console.log('IndexedDB: Success.');
    // Check if we have pending items to sync on startup
    syncOfflineSales();
};

request.onerror = (event) => {
    console.error('IndexedDB Error:', event.target.error);
};

// ── Save Sale to IndexedDB ─────────────────────────────────────────────
async function saveSaleOffline(saleData) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);

        const sale = {
            data: saleData,
            timestamp: new Date().toISOString(),
            synced: false
        };

        const addRequest = store.add(sale);
        addRequest.onsuccess = () => {
            console.log('Sale saved offline.');
            resolve(true);
        };
        addRequest.onerror = () => reject(addRequest.error);
    });
}

// ── Sync Offline Sales to Server ───────────────────────────────────────
async function syncOfflineSales() {
    if (!navigator.onLine) return;

    const transaction = db.transaction([STORE_NAME], 'readonly');
    const store = transaction.objectStore(STORE_NAME);
    const getAllRequest = store.getAll();

    getAllRequest.onsuccess = async () => {
        const sales = getAllRequest.result.filter(s => !s.synced);
        if (sales.length === 0) return;

        console.log(`Syncing ${sales.length} offline sales...`);

        for (const sale of sales) {
            try {
                const response = await fetch('/billing/complete', {
                    method: 'POST',
                    body: new URLSearchParams(sale.data),
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-Offline-Sync': 'true' // Custom header to track sync source
                    }
                });

                if (response.ok) {
                    await deleteSale(sale.id);
                    console.log(`Sale ${sale.id} synced and removed from local storage.`);
                }
            } catch (err) {
                console.error(`Failed to sync sale ${sale.id}:`, err);
            }
        }
    };
}

async function deleteSale(id) {
    return new Promise((resolve) => {
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        store.delete(id).onsuccess = () => resolve();
    });
}

// ── Listen for Online event to trigger sync ────────────────────────────
window.addEventListener('online', () => {
    console.log('Network restored. Triggering sync...');
    syncOfflineSales();
});

// ── Message Listener from Service Worker ──────────────────────────────
navigator.serviceWorker.addEventListener('message', event => {
    if (event.data && event.data.type === 'TRIGGER_SYNC') {
        console.log('PWA: Received sync trigger from SW.');
        syncOfflineSales();
    }
});

// ── Register Background Sync ──────────────────────────────────────────
async function registerSync() {
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
        try {
            const reg = await navigator.serviceWorker.ready;
            await reg.sync.register('sync-sales');
            console.log('PWA: Background sync registered.');
        } catch (err) {
            console.log('PWA: Background sync registration failed (normal for some browsers).');
        }
    }
}

// ── Intercept Billing Form ─────────────────────────────────────────────
// This is used if the page logic doesn't already handle the offline state.
document.addEventListener('submit', async (e) => {
    if (e.target.action && e.target.action.includes('/billing/complete')) {
        if (!navigator.onLine) {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = {};
            formData.forEach((value, key) => data[key] = value);

            try {
                await saveSaleOffline(data);
                // Register sync tag so SW knows to try later
                await registerSync();

                // Dispatch a toast or alert
                window.dispatchEvent(new CustomEvent('toast', {
                    detail: { message: 'Offline: Sale saved locally. It will sync automatically when Wi-Fi returns.', type: 'warning' }
                }));
                // Optional: redirect to home or clear cart UI
                setTimeout(() => window.location.href = '/', 2000);
            } catch (err) {
                console.error(err);
                alert('Critical Error: Could not save sale offline.');
            }
        }
    }
});
