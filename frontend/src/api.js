export class ApiError extends Error {
  constructor(status, detail, cap) {
    super(typeof detail === 'string' ? detail : (detail && detail.detail) || 'Lỗi máy chủ');
    this.status = status;
    this.detail = detail;
    this.cap = cap || null;
  }
}

/* Gọi API cùng origin (cookie phiên HttpOnly). 401 phát sự kiện 'nq-unauth'. */
export async function api(path, { method = 'GET', body } = {}) {
  const opt = { method, credentials: 'same-origin', headers: {} };
  if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  const res = await fetch('/api/v1' + path, opt);
  if (res.status === 401) window.dispatchEvent(new CustomEvent('nq-unauth'));
  let data = null;
  try { data = await res.json(); } catch (e) { /* thân rỗng */ }
  if (!res.ok) {
    const d = data ? data.detail : null;
    const cap = d && typeof d === 'object' ? d.cap : null;
    throw new ApiError(res.status, d, cap);
  }
  return data;
}