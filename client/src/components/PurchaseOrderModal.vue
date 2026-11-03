<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{ mode === 'view' ? t('purchaseOrder.viewTitle') : t('purchaseOrder.createTitle') }}
            </h3>
            <button class="close-button" :aria-label="t('common.close')" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <form class="modal-form" novalidate @submit.prevent="submit">
            <div class="modal-body">
              <!-- Backlog item context -->
              <div class="context-card">
                <div class="context-name">{{ translateProductName(backlogItem.item_name) }}</div>
                <div class="context-meta">
                  <span>{{ t('purchaseOrder.sku') }}: <span class="mono">{{ backlogItem.item_sku }}</span></span>
                  <span>{{ t('purchaseOrder.orderId') }}: <span class="mono">{{ backlogItem.order_id }}</span></span>
                  <span>{{ t('purchaseOrder.shortage') }}: {{ shortage }} {{ t('purchaseOrder.units') }}</span>
                </div>
              </div>

              <!-- View mode -->
              <template v-if="mode === 'view'">
                <div v-if="loading" class="state-message">{{ t('purchaseOrder.loadingPO') }}</div>
                <div v-else-if="loadError" class="error-message" role="alert">{{ loadError }}</div>
                <div v-else-if="purchaseOrder" class="info-grid">
                  <div class="info-item">
                    <div class="info-label">{{ t('purchaseOrder.supplierName') }}</div>
                    <div class="info-value">{{ purchaseOrder.supplier_name }}</div>
                  </div>
                  <div class="info-item">
                    <div class="info-label">{{ t('purchaseOrder.status') }}</div>
                    <div class="info-value"><span class="badge">{{ purchaseOrder.status }}</span></div>
                  </div>
                  <div class="info-item">
                    <div class="info-label">{{ t('purchaseOrder.quantity') }}</div>
                    <div class="info-value">{{ purchaseOrder.quantity }} {{ t('purchaseOrder.units') }}</div>
                  </div>
                  <div class="info-item">
                    <div class="info-label">{{ t('purchaseOrder.unitCost') }}</div>
                    <div class="info-value">{{ formatMoney(purchaseOrder.unit_cost) }}</div>
                  </div>
                  <div class="info-item">
                    <div class="info-label">{{ t('purchaseOrder.totalCost') }}</div>
                    <div class="info-value">{{ formatMoney(purchaseOrder.quantity * purchaseOrder.unit_cost) }}</div>
                  </div>
                  <div class="info-item">
                    <div class="info-label">{{ t('purchaseOrder.expectedDelivery') }}</div>
                    <div class="info-value">{{ formatDate(purchaseOrder.expected_delivery_date) }}</div>
                  </div>
                  <div class="info-item">
                    <div class="info-label">{{ t('purchaseOrder.createdDate') }}</div>
                    <div class="info-value">{{ formatDate(purchaseOrder.created_date) }}</div>
                  </div>
                  <div class="info-item full">
                    <div class="info-label">{{ t('purchaseOrder.notes') }}</div>
                    <div class="info-value notes">{{ purchaseOrder.notes || t('purchaseOrder.noNotes') }}</div>
                  </div>
                </div>
              </template>

              <!-- Create mode -->
              <template v-else>
                <div class="form-grid">
                  <div class="form-group full">
                    <label for="po-supplier">{{ t('purchaseOrder.supplierName') }} *</label>
                    <input id="po-supplier" v-model="form.supplier_name" type="text" maxlength="200" :class="{ invalid: errors.supplier_name }" />
                    <div v-if="errors.supplier_name" class="field-error">{{ errors.supplier_name }}</div>
                  </div>

                  <div class="form-group">
                    <label for="po-quantity">{{ t('purchaseOrder.quantity') }} *</label>
                    <input id="po-quantity" v-model="form.quantity" type="number" min="1" step="1" :class="{ invalid: errors.quantity }" />
                    <div v-if="errors.quantity" class="field-error">{{ errors.quantity }}</div>
                  </div>

                  <div class="form-group">
                    <label for="po-unit-cost">{{ t('purchaseOrder.unitCost') }} *</label>
                    <input id="po-unit-cost" v-model="form.unit_cost" type="number" min="0" step="0.01" :class="{ invalid: errors.unit_cost }" />
                    <div v-if="errors.unit_cost" class="field-error">{{ errors.unit_cost }}</div>
                  </div>

                  <div class="form-group full">
                    <label for="po-delivery">{{ t('purchaseOrder.expectedDelivery') }} *</label>
                    <input id="po-delivery" v-model="form.expected_delivery_date" type="date" :min="todayLocal()" :class="{ invalid: errors.expected_delivery_date }" />
                    <div v-if="errors.expected_delivery_date" class="field-error">{{ errors.expected_delivery_date }}</div>
                  </div>

                  <div class="form-group full">
                    <label for="po-notes">{{ t('purchaseOrder.notes') }}</label>
                    <textarea id="po-notes" v-model="form.notes" rows="3" maxlength="2000" :placeholder="t('purchaseOrder.notesPlaceholder')"></textarea>
                  </div>
                </div>

                <div v-if="submitError" class="error-message" role="alert">{{ submitError }}</div>
              </template>
            </div>

            <div class="modal-footer">
              <button type="button" class="btn-secondary" @click="close">{{ t('common.close') }}</button>
              <button v-if="mode === 'create'" type="submit" class="btn-primary" :disabled="submitting">
                {{ submitting ? t('purchaseOrder.submitting') : t('purchaseOrder.submit') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const { t, translateProductName, currentLocale } = useI18n()

// Map app locale to a BCP 47 tag for Intl formatting
const intlLocale = computed(() => (currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'))

// Today as YYYY-MM-DD in LOCAL time (toISOString would use UTC and can be off by a day)
const todayLocal = () => {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  backlogItem: { type: Object, default: null },
  mode: { type: String, default: 'create', validator: (v) => ['create', 'view'].includes(v) }
})

const emit = defineEmits(['close', 'po-created'])

const form = reactive({
  supplier_name: '',
  quantity: '',
  unit_cost: '',
  expected_delivery_date: '',
  notes: ''
})
const errors = reactive({})
const submitting = ref(false)
const submitError = ref('')

const purchaseOrder = ref(null)
const loading = ref(false)
const loadError = ref('')

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return Math.max(0, props.backlogItem.quantity_needed - props.backlogItem.quantity_available)
})

const clearErrors = () => {
  Object.keys(errors).forEach((k) => delete errors[k])
}

const resetForm = () => {
  form.supplier_name = ''
  form.quantity = shortage.value > 0 ? shortage.value : ''
  form.unit_cost = ''
  form.expected_delivery_date = ''
  form.notes = ''
  clearErrors()
  submitError.value = ''
  submitting.value = false
}

const loadPurchaseOrder = async () => {
  purchaseOrder.value = null
  loadError.value = ''
  loading.value = true
  // Guard against a stale response if the modal is reopened for another item mid-request
  const requestedId = props.backlogItem.id
  try {
    const po = await api.getPurchaseOrderByBacklogItem(requestedId)
    if (props.backlogItem?.id === requestedId) purchaseOrder.value = po
  } catch (err) {
    if (props.backlogItem?.id !== requestedId) return
    console.error('Failed to load purchase order:', err)
    loadError.value = extractError(err, t('purchaseOrder.loadError'))
  } finally {
    if (props.backlogItem?.id === requestedId) loading.value = false
  }
}

// (Re)initialise whenever the modal opens or switches mode/item
watch(
  () => [props.isOpen, props.mode, props.backlogItem?.id],
  ([open]) => {
    if (!open || !props.backlogItem) return
    if (props.mode === 'view') {
      loadPurchaseOrder()
    } else {
      resetForm()
    }
  },
  { immediate: true }
)

// FastAPI returns `detail` as a string for 404/409 but as a list of objects for 422
const extractError = (err, fallback) => {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : ''
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join('; ')
  }
  return fallback
}

const validate = () => {
  clearErrors()
  if (!form.supplier_name.trim()) errors.supplier_name = t('purchaseOrder.supplierRequired')

  const qty = Number(form.quantity)
  if (form.quantity === '' || form.quantity === null || !Number.isInteger(qty) || qty <= 0) {
    errors.quantity = t('purchaseOrder.quantityInvalid')
  }

  const cost = Number(form.unit_cost)
  if (form.unit_cost === '' || form.unit_cost === null || !Number.isFinite(cost) || cost <= 0) {
    errors.unit_cost = t('purchaseOrder.unitCostInvalid')
  }

  // Date input yields YYYY-MM-DD, or '' when empty/incomplete
  if (!form.expected_delivery_date || isNaN(new Date(form.expected_delivery_date).getTime())) {
    errors.expected_delivery_date = t('purchaseOrder.deliveryRequired')
  } else if (form.expected_delivery_date < todayLocal()) {
    // Both are zero-padded YYYY-MM-DD, so string comparison is chronological
    errors.expected_delivery_date = t('purchaseOrder.deliveryPast')
  }
  return Object.keys(errors).length === 0
}

const submit = async () => {
  if (submitting.value || !validate()) return
  submitError.value = ''
  submitting.value = true
  // Remember which item this request is for; the modal may be closed/reopened for another item mid-request
  const requestedId = props.backlogItem.id
  const payload = {
    backlog_item_id: requestedId,
    supplier_name: form.supplier_name.trim(),
    quantity: Number(form.quantity),
    unit_cost: Number(form.unit_cost),
    expected_delivery_date: form.expected_delivery_date
  }
  const notes = form.notes.trim()
  if (notes) payload.notes = notes

  try {
    const po = await api.createPurchaseOrder(payload)
    // Always emit on success so the parent can update the original row (it looks it up by backlog_item_id
    // and only closes the modal if it is still showing that item)
    emit('po-created', po)
  } catch (err) {
    console.error('Failed to create purchase order:', err)
    // Don't leak a stale error into another item's form
    if (props.backlogItem?.id === requestedId) {
      submitError.value = extractError(err, t('purchaseOrder.createError'))
    }
  } finally {
    if (props.backlogItem?.id === requestedId) submitting.value = false
  }
}

const close = () => {
  emit('close')
}

const formatMoney = (value) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return t('purchaseOrder.notAvailable')
  return n.toLocaleString(intlLocale.value, { style: 'currency', currency: 'USD' })
}

const formatDate = (dateString) => {
  if (!dateString) return t('purchaseOrder.notAvailable')
  // Date-only strings parse as UTC and can shift a day in local time; force local midnight
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(dateString) ? `${dateString}T00:00:00` : dateString
  const date = new Date(normalized)
  if (isNaN(date.getTime())) return t('purchaseOrder.notAvailable')
  return date.toLocaleDateString(intlLocale.value, { year: 'numeric', month: 'long', day: 'numeric' })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 640px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-form {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
}

.context-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
}

.context-name {
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 0.5rem;
}

.context-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

.mono {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.form-grid,
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem;
}

.full {
  grid-column: 1 / -1;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-group label,
.info-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.form-group input,
.form-group textarea {
  padding: 0.625rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.875rem;
  font-family: inherit;
  color: #0f172a;
  background: white;
}

.form-group textarea {
  resize: vertical;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.form-group input.invalid {
  border-color: #ef4444;
}

.field-error {
  font-size: 0.75rem;
  color: #dc2626;
}

.error-message {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
}

.state-message {
  padding: 2rem 0;
  text-align: center;
  color: #64748b;
  font-size: 0.875rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.info-value.notes {
  white-space: pre-wrap;
  font-weight: 400;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 6px;
  font-size: 0.813rem;
  font-weight: 600;
  background: #fef3c7;
  color: #92400e;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary,
.btn-primary {
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #334155;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  background: #0f172a;
  border: 1px solid #0f172a;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
