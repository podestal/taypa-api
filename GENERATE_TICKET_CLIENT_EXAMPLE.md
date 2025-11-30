# Client-side Implementation for Generate Ticket PDF

## Axios Request Examples

### Option 1: Print (Recommended for Tickets) 🔥

Opens PDF in new window and automatically triggers print dialog.

```javascript
import axios from 'axios';

async function generateAndPrintTicket(orderItems, orderNumber = null, customerName = null) {
  try {
    const response = await axios.post(
      `${API_BASE_URL}/taxes/documents/generate-ticket/`,
      {
        order_items: orderItems,
        order_number: orderNumber,
        customer_name: customerName,
      },
      {
        responseType: 'blob', // Important: handle binary data
        headers: {
          'Authorization': `Bearer ${yourAuthToken}`,
          'Content-Type': 'application/json',
        },
      }
    );

    // Create blob URL
    const blob = new Blob([response.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);

    // Open in new window and print
    const printWindow = window.open(url, '_blank');
    
    if (printWindow) {
      printWindow.onload = () => {
        setTimeout(() => {
          printWindow.print();
          // Clean up after printing (optional)
          // window.URL.revokeObjectURL(url);
        }, 250);
      };
    } else {
      console.error('Failed to open print window. Popup blocked?');
      // Fallback: download
      downloadPDF(blob, orderNumber);
    }
  } catch (error) {
    console.error('Error generating ticket:', error);
    // Handle error (show notification, etc.)
  }
}

// Usage
generateAndPrintTicket(
  [
    { id: '1', name: 'Producto 1', quantity: 2, cost: 10.00 },
    { id: '2', name: 'Producto 2', quantity: 1, cost: 25.50 },
  ],
  'ORD-001',
  'Juan Pérez'
);
```

### Option 2: Open in New Tab (View Only)

Opens PDF in new tab for viewing (user can print manually).

```javascript
async function generateAndViewTicket(orderItems, orderNumber = null, customerName = null) {
  try {
    const response = await axios.post(
      `${API_BASE_URL}/taxes/documents/generate-ticket/`,
      {
        order_items: orderItems,
        order_number: orderNumber,
        customer_name: customerName,
      },
      {
        responseType: 'blob',
        headers: {
          'Authorization': `Bearer ${yourAuthToken}`,
        },
      }
    );

    const blob = new Blob([response.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    
    // Open in new tab
    window.open(url, '_blank');
    
    // Clean up URL after a delay (optional)
    // setTimeout(() => window.URL.revokeObjectURL(url), 100);
  } catch (error) {
    console.error('Error generating ticket:', error);
  }
}
```

### Option 3: Download PDF

Downloads PDF file directly to user's computer.

```javascript
async function generateAndDownloadTicket(orderItems, orderNumber = null, customerName = null) {
  try {
    const response = await axios.post(
      `${API_BASE_URL}/taxes/documents/generate-ticket/`,
      {
        order_items: orderItems,
        order_number: orderNumber,
        customer_name: customerName,
      },
      {
        responseType: 'blob',
        headers: {
          'Authorization': `Bearer ${yourAuthToken}`,
        },
      }
    );

    const blob = new Blob([response.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    
    // Create temporary link and trigger download
    const link = document.createElement('a');
    link.href = url;
    link.download = `ticket_${orderNumber || 'ticket'}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Clean up
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Error generating ticket:', error);
  }
}
```

## Complete Utility Function (All Options)

```javascript
import axios from 'axios';

/**
 * Generate ticket PDF with different display options
 * @param {Array} orderItems - Array of order items
 * @param {Object} options - Options object
 * @param {string} options.action - 'print' | 'view' | 'download'
 * @param {string} options.orderNumber - Optional order number
 * @param {string} options.customerName - Optional customer name
 * @param {string} options.apiBaseUrl - API base URL
 * @param {string} options.authToken - Auth token
 */
async function generateTicket(orderItems, options = {}) {
  const {
    action = 'print', // Default: print
    orderNumber = null,
    customerName = null,
    apiBaseUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000',
    authToken = null,
  } = options;

  try {
    // Show loading state (if you have one)
    // setLoading(true);

    const response = await axios.post(
      `${apiBaseUrl}/taxes/documents/generate-ticket/`,
      {
        order_items: orderItems,
        order_number: orderNumber,
        customer_name: customerName,
      },
      {
        responseType: 'blob',
        headers: {
          ...(authToken && { Authorization: `Bearer ${authToken}` }),
          'Content-Type': 'application/json',
        },
      }
    );

    const blob = new Blob([response.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    const filename = `ticket_${orderNumber || new Date().toISOString().slice(0, 10)}.pdf`;

    switch (action) {
      case 'print': {
        const printWindow = window.open(url, '_blank');
        if (printWindow) {
          printWindow.onload = () => {
            setTimeout(() => {
              printWindow.print();
            }, 250);
          };
        } else {
          // Popup blocked, fallback to download
          downloadPDF(blob, filename);
        }
        break;
      }

      case 'view': {
        window.open(url, '_blank');
        break;
      }

      case 'download': {
        downloadPDF(blob, filename);
        window.URL.revokeObjectURL(url);
        break;
      }

      default:
        console.warn(`Unknown action: ${action}`);
    }

    // Hide loading state
    // setLoading(false);
  } catch (error) {
    console.error('Error generating ticket:', error);
    
    // Handle error
    if (error.response) {
      // Server responded with error
      console.error('Error response:', error.response.data);
    } else if (error.request) {
      // Request made but no response
      console.error('No response received');
    } else {
      // Error setting up request
      console.error('Error:', error.message);
    }
    
    // Hide loading state
    // setLoading(false);
    
    // Show error notification
    // addNotification('Error generating ticket', 'error');
  }
}

// Helper function for download
function downloadPDF(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

// Export for use
export { generateTicket };
```

## React Hook Example

```javascript
import { useState } from 'react';
import { generateTicket } from './utils/ticketGenerator';

function useTicketGenerator() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const printTicket = async (orderItems, orderNumber, customerName) => {
    setLoading(true);
    setError(null);
    
    try {
      await generateTicket(orderItems, {
        action: 'print',
        orderNumber,
        customerName,
        authToken: getAuthToken(), // Your auth function
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return { printTicket, loading, error };
}

// Usage in component
function OrderComponent() {
  const { printTicket, loading } = useTicketGenerator();

  const handlePrintTicket = () => {
    printTicket(
      orderItems,
      orderInfo.orderNumber,
      customerInfo.name
    );
  };

  return (
    <button onClick={handlePrintTicket} disabled={loading}>
      {loading ? 'Generating...' : 'Print Ticket'}
    </button>
  );
}
```

## Key Points:

1. **Use `responseType: 'blob'`** - Required to handle PDF binary data
2. **Authorization header** - Include your auth token
3. **Blob URL** - Create object URL from blob for display
4. **Cleanup** - Revoke object URLs to free memory (optional but recommended)
5. **Error handling** - Handle network errors, auth errors, etc.
6. **Print timing** - Small delay (250ms) ensures PDF is fully loaded before print

## Recommendation:

For ticket printing, use **Option 1 (Print)** as it provides the best UX - automatically opens and prints, which is what you want for kitchen tickets!

