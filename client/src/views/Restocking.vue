<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const { t, currentCurrency, currentLocale } = useI18n()

const loading = ref(true)
const error = ref(null)
const forecasts = ref([])

// Budget is always held in USD (the backend currency); formatting converts for display only.
const budget = ref(0)
const BUDGET_STEP = 500

// User overrides keyed by SKU: { included?: boolean, quantity?: number }.
// A missing field means "use the computed recommendation".
const overrides = reactive({})

const submitting = ref(false)
const submitError = ref(null)
const confirmation = ref(null)

// Slider max: cost of everything at full forecasted demand, rounded up to the next step.
const maxBudget = computed(() => {
  const total = forecasts.value.reduce((sum, f) => sum + f.forecasted_demand * f.unit_cost, 0)
  return Math.max(BUDGET_STEP, Math.ceil(total / BUDGET_STEP) * BUDGET_STEP)
})

// formatCurrency puts the sign after the symbol ("$-89"), so format the absolute
// value and prefix the minus ourselves to get "-$89" when over budget.
const fmt = (amount) => (amount < 0 ? '-' : '') + formatCurrency(Math.abs(amount), currentCurrency.value)
const fmtExact = (amount) => formatCurrencyWithDecimals(amount, currentCurrency.value, 2)

// Higher rank = more urgent. Unknown trends sort last.
const TREND_RANK = { increasing: 0, stable: 1, decreasing: 2 }

// Items ordered by trend, then by forecast growth (forecasted - current) descending.
const rankedForecasts = computed(() => {
  return [...forecasts.value].sort((a, b) => {
    const ra = TREND_RANK[a.trend] ?? 3
    const rb = TREND_RANK[b.trend] ?? 3
    if (ra !== rb) return ra - rb
    return (b.forecasted_demand - b.current_demand) - (a.forecasted_demand - a.current_demand)
  })
})

// Greedy budget fill in ranked order. Returns { [sku]: suggestedQty }.
const recommendations = computed(() => {
  let remaining = budget.value
  const result = {}
  for (const f of rankedForecasts.value) {
    let qty = 0
    const fullCost = f.forecasted_demand * f.unit_cost
    if (fullCost <= remaining + 1e-9) {
      qty = f.forecasted_demand
    } else if (f.unit_cost > 0) {
      // Partial fill; the epsilon guards against float error (e.g. 2.9999999 -> 2).
      qty = Math.max(0, Math.floor(remaining / f.unit_cost + 1e-9))
    }
    result[f.item_sku] = qty
    remaining -= qty * f.unit_cost
  }
  return result
})

// Table rows: recommendation merged with user overrides. All items are shown so
// non-recommended ones can be added manually.
const rows = computed(() => {
  return rankedForecasts.value.map(f => {
    const o = overrides[f.item_sku] || {}
    const suggested = recommendations.value[f.item_sku] || 0
    const quantity = o.quantity !== undefined ? o.quantity : suggested
    const included = o.included !== undefined ? o.included : suggested > 0
    return {
      ...f,
      quantity,
      included,
      lineTotal: quantity * f.unit_cost
    }
  })
})

const selectedRows = computed(() => rows.value.filter(r => r.included && r.quantity > 0))
const selectedTotal = computed(() => selectedRows.value.reduce((sum, r) => sum + r.lineTotal, 0))
const remainingBudget = computed(() => budget.value - selectedTotal.value)
// Tolerance of half a cent so float noise never triggers a false over-budget state.
const isOverBudget = computed(() => selectedTotal.value > budget.value + 0.005)
const leadTime = computed(() => selectedRows.value.reduce((max, r) => Math.max(max, r.lead_time_days), 0))
const canPlaceOrder = computed(() => !submitting.value && selectedRows.value.length > 0 && !isOverBudget.value)

// Changing the budget discards manual edits and recomputes suggestions.
watch(budget, () => {
  Object.keys(overrides).forEach(k => delete overrides[k])
})

const toggleItem = (row, checked) => {
  const o = overrides[row.item_sku] || {}
  o.included = checked
  // Ticking a row that has no quantity pre-fills the forecasted demand so the tick has an effect.
  if (checked && row.quantity <= 0) o.quantity = row.forecasted_demand
  overrides[row.item_sku] = o
}

const setQuantity = (row, rawValue) => {
  // Number inputs yield '' while empty; treat anything invalid as 0 and keep whole units only.
  const parsed = Math.floor(Number(rawValue))
  const quantity = Number.isFinite(parsed) && parsed > 0 ? parsed : 0
  // Entering a quantity ticks the row; clearing it unticks.
  overrides[row.item_sku] = { ...(overrides[row.item_sku] || {}), quantity, included: quantity > 0 }
}

const formatDate = (value) => {
  const date = new Date(value)
  if (!value || isNaN(date.getTime())) return '-'
  return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
    year: 'numeric', month: 'short', day: 'numeric'
  })
}

// FastAPI returns detail as a string (400/404) or an array of {msg} objects (422).
const extractError = (err) => {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => (typeof d === 'string' ? d : d.msg)).filter(Boolean).join('; ')
  }
  return err?.message || 'Unknown error'
}

const loadForecasts = async () => {
  try {
    loading.value = true
    error.value = null
    forecasts.value = await api.getDemandForecasts()
    // Default to roughly half of max, snapped to the slider step.
    budget.value = Math.round(maxBudget.value / 2 / BUDGET_STEP) * BUDGET_STEP
  } catch (err) {
    error.value = 'Failed to load demand forecasts: ' + err.message
  } finally {
    loading.value = false
  }
}

const placeOrder = async () => {
  if (!canPlaceOrder.value) return
  submitting.value = true
  submitError.value = null
  confirmation.value = null
  try {
    confirmation.value = await api.createRestockingOrder({
      items: selectedRows.value.map(r => ({ sku: r.item_sku, quantity: r.quantity })),
      budget: budget.value
    })
    // Clear manual edits so the table returns to the computed recommendation.
    Object.keys(overrides).forEach(k => delete overrides[k])
  } catch (err) {
    submitError.value = t('restocking.submitFailed') + extractError(err)
  } finally {
    submitting.value = false
  }
}

onMounted(loadForecasts)
</script>

<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="budget-header">
          <label for="budget-slider" class="budget-label">{{ t('restocking.budget') }}</label>
          <span class="budget-value">{{ fmt(budget) }}</span>
        </div>
        <input
          id="budget-slider"
          v-model.number="budget"
          type="range"
          min="0"
          :max="maxBudget"
          :step="BUDGET_STEP"
          class="budget-slider"
        />
        <div class="budget-scale">
          <span>{{ fmt(0) }}</span>
          <span>{{ fmt(maxBudget) }}</span>
        </div>
        <p class="hint">{{ t('restocking.budgetHint') }}</p>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.selectedTotal') }}</div>
          <div class="stat-value">{{ fmt(selectedTotal) }}</div>
        </div>
        <div :class="['stat-card', isOverBudget ? 'danger' : 'success']">
          <div class="stat-label">{{ t('restocking.remaining') }}</div>
          <div class="stat-value" :class="{ 'over-budget': isOverBudget }">{{ fmt(remainingBudget) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.leadTime') }}</div>
          <div class="stat-value">{{ t('restocking.days', { count: leadTime }) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommended') }}</h3>
        </div>
        <div v-if="rows.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th class="col-check">{{ t('restocking.include') }}</th>
                <th>{{ t('restocking.sku') }}</th>
                <th>{{ t('restocking.itemName') }}</th>
                <th>{{ t('restocking.trend') }}</th>
                <th class="num">{{ t('restocking.unitCost') }}</th>
                <th class="num">{{ t('restocking.quantity') }}</th>
                <th class="num">{{ t('restocking.lineTotal') }}</th>
                <th class="num">{{ t('restocking.leadTimeDays') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.item_sku" :class="{ 'row-excluded': !row.included }">
                <td class="col-check">
                  <input
                    type="checkbox"
                    :checked="row.included"
                    :aria-label="t('restocking.include') + ' ' + row.item_sku"
                    @change="toggleItem(row, $event.target.checked)"
                  />
                </td>
                <td><strong>{{ row.item_sku }}</strong></td>
                <td>{{ row.item_name }}</td>
                <td>
                  <span :class="['badge', row.trend]">{{ t(`trends.${row.trend}`) }}</span>
                </td>
                <td class="num">{{ fmtExact(row.unit_cost) }}</td>
                <td class="num">
                  <input
                    type="number"
                    min="0"
                    step="1"
                    class="qty-input"
                    :value="row.quantity"
                    :aria-label="t('restocking.quantity') + ' ' + row.item_sku"
                    @input="setQuantity(row, $event.target.value)"
                  />
                  <!-- @input (not @change) so totals and the over-budget state update while typing,
                       not only after the field loses focus. -->
                </td>
                <td class="num">{{ fmtExact(row.included ? row.lineTotal : 0) }}</td>
                <td class="num">{{ row.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-footer">
          <p v-if="isOverBudget" class="message danger-text">
            {{ t('restocking.overBudget', { amount: fmtExact(-remainingBudget) }) }}
          </p>
          <p v-else-if="selectedRows.length === 0" class="message muted">{{ t('restocking.nothingSelected') }}</p>
          <button type="button" class="btn-primary" :disabled="!canPlaceOrder" @click="placeOrder">
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="submitError" class="alert alert-error" role="alert">{{ submitError }}</div>

        <div v-if="confirmation" class="alert alert-success" role="status">
          <strong>{{ t('restocking.success') }}</strong>
          <div class="confirm-details">
            <span>{{ t('restocking.successOrderNumber') }}: <strong>{{ confirmation.order_number }}</strong></span>
            <span>{{ t('restocking.leadTime') }}: {{ t('restocking.days', { count: confirmation.lead_time_days }) }}</span>
            <span>{{ t('restocking.successExpected') }}: {{ formatDate(confirmation.expected_delivery) }}</span>
          </div>
          <router-link to="/orders" class="confirm-link">{{ t('restocking.viewOrders') }}</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.budget-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-slider {
  width: 100%;
  accent-color: #3b82f6;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

.hint {
  margin-top: 0.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

.over-budget {
  color: #dc2626;
}

th.num,
td.num {
  text-align: right;
}

.col-check {
  width: 70px;
  text-align: center;
}

.row-excluded td {
  color: #94a3b8;
}

.qty-input {
  width: 90px;
  padding: 0.375rem 0.5rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  text-align: right;
  font-size: 0.875rem;
  color: #0f172a;
}

.qty-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.empty-state {
  padding: 1.5rem;
  color: #64748b;
  text-align: center;
}

.order-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
}

.message {
  margin: 0;
  font-size: 0.875rem;
  margin-right: auto;
}

.danger-text {
  color: #dc2626;
  font-weight: 500;
}

.muted {
  color: #64748b;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.alert {
  margin-top: 1rem;
  padding: 0.875rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
}

.alert-error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.alert-success {
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.confirm-details {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  margin: 0.5rem 0;
}

.confirm-link {
  color: #047857;
  font-weight: 600;
  text-decoration: underline;
}
</style>
