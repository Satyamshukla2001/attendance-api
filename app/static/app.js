const $ = (selector) => document.querySelector(selector);
const state = { employees: [], selectedEmployee: "", noticeTimer: null };

const monthInput = $("#month-filter");
const employeeSelect = $("#employee-select");
const attendanceFilter = $("#attendance-filter");
const punchInButton = $("#punch-in-button");
const punchOutButton = $("#punch-out-button");

function localDateString(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const value = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${value.year}-${value.month}-${value.day}`;
}

function currentMonth() {
  return localDateString().slice(0, 7);
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
}

function initials(name) {
  return String(name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] || "")
    .join("")
    .toUpperCase();
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00+05:30`);
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
  }).format(date);
}

function formatTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(new Date(value));
}

async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(", ")
      : detail || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

function showNotice(message, kind = "error") {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("success", kind === "success");
  notice.hidden = false;
  window.clearTimeout(state.noticeTimer);
  state.noticeTimer = window.setTimeout(() => {
    notice.hidden = true;
  }, 6500);
}

function employeeName(employeeId) {
  return (
    state.employees.find((employee) => employee.employee_id === employeeId)
      ?.name || employeeId
  );
}

function setEmployeeOptions() {
  const options = state.employees
    .map(
      (employee) =>
        `<option value="${escapeHtml(employee.employee_id)}">${escapeHtml(employee.name)} · ${escapeHtml(employee.department)}</option>`,
    )
    .join("");
  employeeSelect.innerHTML = `<option value="">Choose a team member</option>${options}`;
  attendanceFilter.innerHTML = `<option value="">Everyone</option>${options}`;
}

function setStat(id, value) {
  $(`#${id}`).textContent = value;
}

function renderSummary(rows) {
  const summary = $("#team-summary");
  if (!rows.length) {
    summary.innerHTML =
      '<div class="team-empty">No attendance recorded for this period yet.</div>';
    $("#team-count").textContent = "No attendance this period";
    return;
  }
  summary.innerHTML = rows
    .map(
      (row) => `
    <div class="team-row">
      <div class="team-person">
        <span class="person-avatar">${escapeHtml(initials(row.name))}</span>
        <span><span class="team-name">${escapeHtml(row.name)}</span><span class="team-department">${escapeHtml(row.department)}</span></span>
      </div>
      <span class="team-days"><strong>${Number(row.days_present) || 0}</strong> days</span>
      <span class="team-hours"><strong>${Number(row.total_hours || 0).toFixed(1)}h</strong>${Number(row.late_days) || 0} late</span>
    </div>
  `,
    )
    .join("");
  $("#team-count").textContent =
    `${rows.length} ${rows.length === 1 ? "team member" : "team members"}`;
}

function renderAttendance(rows) {
  const table = $("#attendance-rows");
  if (!rows.length) {
    table.innerHTML =
      '<tr><td class="empty-cell" colspan="6">No attendance records found.</td></tr>';
    $("#attendance-count").textContent = "No matching shifts";
    return;
  }
  table.innerHTML = rows
    .map((row) => {
      const employee = state.employees.find(
        (person) => person.employee_id === row.employee_id,
      );
      const hours = Number.isFinite(Number(row.duration_minutes))
        ? `${(Number(row.duration_minutes) / 60).toFixed(1)}h`
        : "—";
      const open = row.status === "open";
      return `
      <tr>
        <td><span class="person-cell"><span class="person-avatar">${escapeHtml(initials(employee?.name || row.employee_id))}</span><span><span class="person-name">${escapeHtml(employee?.name || row.employee_id)}</span><span class="person-id">${escapeHtml(row.employee_id)}</span></span></span></td>
        <td>${escapeHtml(formatDate(row.work_date))}</td>
        <td>${escapeHtml(formatTime(row.punch_in))}</td>
        <td>${escapeHtml(formatTime(row.punch_out))}</td>
        <td class="hours-cell">${hours}</td>
        <td><span class="status-pill${open ? " open" : ""}">${open ? "In progress" : "Complete"}</span></td>
      </tr>
    `;
    })
    .join("");
  $("#attendance-count").textContent =
    `Showing ${rows.length} recent ${rows.length === 1 ? "shift" : "shifts"}`;
}

async function loadStats() {
  const month = monthInput.value || currentMonth();
  $("#summary-period").textContent = new Intl.DateTimeFormat("en", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${month}-01T00:00:00Z`));
  const [monthly, departments] = await Promise.all([
    request(`/analytics/monthly-summary?month=${encodeURIComponent(month)}`),
    request(`/analytics/department-summary?month=${encodeURIComponent(month)}`),
  ]);
  const hours = monthly.reduce(
    (sum, row) => sum + (Number(row.total_hours) || 0),
    0,
  );
  const days = monthly.reduce(
    (sum, row) => sum + (Number(row.days_present) || 0),
    0,
  );
  const lateDays = monthly.reduce(
    (sum, row) => sum + (Number(row.late_days) || 0),
    0,
  );
  const activeTeamCount = departments.reduce(
    (sum, row) => sum + (Number(row.headcount_active) || 0),
    0,
  );
  setStat("employee-count", activeTeamCount);
  setStat(
    "hours-total",
    `${hours.toLocaleString("en-IN", { maximumFractionDigits: 1 })}h`,
  );
  setStat("days-total", days.toLocaleString("en-IN"));
  setStat("late-total", lateDays.toLocaleString("en-IN"));
  renderSummary(monthly);
}

async function loadAttendance() {
  const params = new URLSearchParams({ limit: "50" });
  const employeeId = attendanceFilter.value;
  if (employeeId) params.set("employee_id", employeeId);
  renderAttendance(await request(`/attendance?${params}`));
}

async function updateShiftStatus() {
  const employeeId = employeeSelect.value;
  state.selectedEmployee = employeeId;
  if (!employeeId) {
    punchInButton.disabled = true;
    punchOutButton.disabled = true;
    $("#shift-status").textContent =
      "Choose a team member to see their shift status.";
    return;
  }
  const records = await request(
    `/attendance?employee_id=${encodeURIComponent(employeeId)}&limit=50`,
  );
  const openShift = records.find((record) => record.status === "open");
  punchInButton.disabled = Boolean(openShift);
  punchOutButton.disabled = !openShift;
  $("#shift-status").textContent = openShift
    ? `Currently clocked in since ${formatTime(openShift.punch_in)}.`
    : `${employeeName(employeeId)} has no open shift.`;
}

async function punch(action) {
  const employeeId = employeeSelect.value;
  if (!employeeId) return;
  punchInButton.disabled = true;
  punchOutButton.disabled = true;
  try {
    const result = await request(`/attendance/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_id: employeeId }),
    });
    showNotice(
      `${employeeName(employeeId)} punched ${action === "punch-in" ? "in" : "out"} at ${formatTime(action === "punch-in" ? result.punch_in : result.punch_out)}.`,
      "success",
    );
    await Promise.all([loadAttendance(), loadStats(), updateShiftStatus()]);
  } catch (error) {
    showNotice(error.message);
    await updateShiftStatus().catch((statusError) =>
      showNotice(statusError.message),
    );
  }
}

async function loadDashboard() {
  const refresh = $("#refresh-button");
  refresh.classList.add("loading");
  try {
    const employees = await request("/attendance/employees");
    state.employees = employees;
    setEmployeeOptions();
    await Promise.all([loadStats(), loadAttendance()]);
    await updateShiftStatus();
  } catch (error) {
    showNotice(`Could not load dashboard: ${error.message}`);
    $("#attendance-rows").innerHTML =
      '<tr><td class="empty-cell" colspan="6">Unable to load attendance.</td></tr>';
    $("#team-summary").innerHTML =
      '<div class="team-empty">Unable to load team summary.</div>';
  } finally {
    refresh.classList.remove("loading");
  }
}

monthInput.value = currentMonth();
$("#today-label").textContent = new Intl.DateTimeFormat("en", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "Asia/Kolkata",
})
  .format(new Date())
  .toUpperCase();

employeeSelect.addEventListener("change", () => {
  updateShiftStatus().catch((error) => showNotice(error.message));
});
attendanceFilter.addEventListener("change", () => {
  loadAttendance().catch((error) => showNotice(error.message));
});
$("#clear-filter").addEventListener("click", (event) => {
  event.preventDefault();
  attendanceFilter.value = "";
  loadAttendance().catch((error) => showNotice(error.message));
});
monthInput.addEventListener("change", () => {
  loadStats().catch((error) => showNotice(error.message));
});
$("#refresh-button").addEventListener("click", loadDashboard);
punchInButton.addEventListener("click", () => punch("punch-in"));
punchOutButton.addEventListener("click", () => punch("punch-out"));

loadDashboard();
