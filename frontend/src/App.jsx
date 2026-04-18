import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  applyMerchantMappingsBulk,
  createGoal,
  exportSummaryPdfUrl,
  exportTransactionsXlsxUrl,
  generateInsights,
  getAiAdvice,
  getAiDiagnostics,
  getGoals,
  getBudgets,
  getDashboard,
  getForecast,
  getInsights,
  getMerchantMappings,
  getPremiumOverview,
  getTransactions,
  updateCategory,
  updateGoalProgress,
  uploadStatement,
  upsertBudget,
} from "./api";

const DEFAULT_CATEGORIES = ["Food", "Rent", "Travel", "Shopping", "Bills", "Investment", "Salary", "Others"];
const PIE_COLORS = ["#0f766e", "#0d9488", "#0891b2", "#2563eb", "#16a34a", "#ca8a04", "#ea580c", "#64748b"];

const money = (n) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(n || 0));

function Card({ title, action, children, className = "" }) {
  return (
    <section className={`card-surface ${className}`}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-wide text-slate-700">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function App() {
  const [dark, setDark] = useState(false);
  const [file, setFile] = useState(null);
  const [bankName, setBankName] = useState("");
  const [filters, setFilters] = useState({ start: "", end: "", category: "" });
  const [dashboard, setDashboard] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [insights, setInsights] = useState([]);
  const [aiAdvice, setAiAdvice] = useState(null);
  const [aiDiagnostics, setAiDiagnostics] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [premium, setPremium] = useState(null);
  const [goals, setGoals] = useState([]);
  const [budgets, setBudgets] = useState([]);
  const [categories, setCategories] = useState(DEFAULT_CATEGORIES);
  const [merchantModalOpen, setMerchantModalOpen] = useState(false);
  const [merchantMappings, setMerchantMappings] = useState([]);
  const [merchantDraft, setMerchantDraft] = useState({});
  const [merchantSearch, setMerchantSearch] = useState("");
  const [customCategory, setCustomCategory] = useState("");
  const [txnSort, setTxnSort] = useState({ key: "txn_date", dir: "desc" });
  const [budgetForm, setBudgetForm] = useState({
    category: "Food",
    amount: "",
    month: new Date().toISOString().slice(0, 7),
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [goalForm, setGoalForm] = useState({
    title: "Emergency Fund",
    target_amount: "",
    current_amount: "",
    target_date: "",
  });

  const queryParams = useMemo(() => {
    const params = {};
    if (filters.start) params.start = filters.start;
    if (filters.end) params.end = filters.end;
    if (filters.category) params.category = filters.category;
    return params;
  }, [filters]);

  const sortedTransactions = useMemo(() => {
    const rows = [...transactions];
    const { key, dir } = txnSort;
    const factor = dir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      if (key === "txn_date") {
        const av = new Date(a.txn_date).getTime();
        const bv = new Date(b.txn_date).getTime();
        return (av - bv) * factor;
      }
      if (key === "amount") {
        return (Number(a.amount) - Number(b.amount)) * factor;
      }
      const av = String(a[key] ?? "").toLowerCase();
      const bv = String(b[key] ?? "").toLowerCase();
      return av.localeCompare(bv) * factor;
    });
    return rows;
  }, [transactions, txnSort]);

  const toggleTxnSort = (key) => {
    setTxnSort((prev) => {
      if (prev.key === key) {
        return { key, dir: prev.dir === "asc" ? "desc" : "asc" };
      }
      return { key, dir: key === "txn_date" ? "desc" : "asc" };
    });
  };

  const sortLabel = (key, label) => {
    if (txnSort.key !== key) return label;
    return `${label} ${txnSort.dir === "asc" ? "▲" : "▼"}`;
  };

  const mergeCategories = (...sets) => {
    const merged = new Set(DEFAULT_CATEGORIES);
    sets.forEach((rows) => {
      (rows || []).forEach((item) => {
        if (typeof item === "string" && item.trim()) merged.add(item.trim());
        if (item?.category && String(item.category).trim()) merged.add(String(item.category).trim());
      });
    });
    setCategories(Array.from(merged));
  };

  const loadAll = async () => {
    const [d, t, i, f, p, g, b] = await Promise.allSettled([
      getDashboard(queryParams),
      getTransactions(queryParams),
      getInsights(),
      getForecast(),
      getPremiumOverview(),
      getGoals(),
      getBudgets(budgetForm.month),
    ]);

    if (d.status === "fulfilled") setDashboard(d.value);
    if (t.status === "fulfilled") setTransactions(t.value);
    if (i.status === "fulfilled") setInsights(i.value);
    if (f.status === "fulfilled") setForecast(f.value);
    if (p.status === "fulfilled") setPremium(p.value);
    if (g.status === "fulfilled") setGoals(g.value);
    if (b.status === "fulfilled") setBudgets(b.value);

    mergeCategories(
      t.status === "fulfilled" ? t.value : [],
      b.status === "fulfilled" ? b.value : [],
      g.status === "fulfilled" ? g.value : []
    );

    const failed = [d, t, i, f, p, g, b].some((x) => x.status === "rejected");
    if (failed) setMessage("Some panels failed to load. Please check backend logs.");

    // Load AI features without blocking core dashboard rendering.
    getAiAdvice()
      .then((data) => setAiAdvice(data))
      .catch(() => setAiAdvice({ summary: "AI advice unavailable right now.", what_to_do: [], what_to_avoid: [] }));
    getAiDiagnostics()
      .then((data) => setAiDiagnostics(data))
      .catch(() => setAiDiagnostics({ ok: false, message: "AI diagnostics unavailable (timeout or LLM offline)." }));
  };

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    loadAll();
  }, [filters.start, filters.end, filters.category]);

  const onUpload = async () => {
    if (!file) return;
    setLoading(true);
    setMessage("");
    try {
      const result = await uploadStatement(file, bankName);
      setMessage(`Uploaded ${result.inserted} rows.`);
      await generateInsights();
      await loadAll();
    } catch (e) {
      setMessage(e.response?.data?.detail ?? "Upload failed.");
    } finally {
      setLoading(false);
    }
  };

  const onSaveBudget = async () => {
    if (!budgetForm.amount) return;
    await upsertBudget({ ...budgetForm, amount: Number(budgetForm.amount) });
    setBudgetForm((prev) => ({ ...prev, amount: "" }));
    await loadAll();
  };

  const onUpdateCategory = async (id, category, keyword) => {
    await updateCategory(id, category, keyword);
    await loadAll();
  };

  const onCreateGoal = async () => {
    if (!goalForm.title || !goalForm.target_amount) return;
    await createGoal({
      title: goalForm.title,
      target_amount: Number(goalForm.target_amount),
      current_amount: Number(goalForm.current_amount || 0),
      target_date: goalForm.target_date || null,
    });
    setGoalForm((prev) => ({ ...prev, target_amount: "", current_amount: "" }));
    await loadAll();
  };

  const onAddGoalProgress = async (goalId, current) => {
    const next = window.prompt("Update goal progress amount", String(current ?? 0));
    if (next === null) return;
    const value = Number(next);
    if (Number.isNaN(value) || value < 0) return;
    await updateGoalProgress(goalId, value);
    await loadAll();
  };

  const openMerchantManager = async () => {
    const mappings = await getMerchantMappings();
    setMerchantMappings(mappings);
    setMerchantDraft(
      mappings.reduce((acc, row) => {
        acc[row.merchant] = row.category;
        return acc;
      }, {})
    );
    mergeCategories(mappings);
    setMerchantSearch("");
    setMerchantModalOpen(true);
  };

  const saveMerchantMappings = async () => {
    const payload = merchantMappings
      .map((m) => ({ merchant: m.merchant, category: (merchantDraft[m.merchant] || "").trim() }))
      .filter((m) => m.category);
    if (payload.length) await applyMerchantMappingsBulk(payload);
    setMerchantModalOpen(false);
    await loadAll();
  };

  const addCustomCategory = () => {
    const value = customCategory.trim();
    if (!value) return;
    if (!categories.includes(value)) setCategories((prev) => [...prev, value]);
    setCustomCategory("");
  };

  const topMerchants = dashboard?.top_merchants ?? [];
  const budgetStatus = dashboard?.budget_status ?? [];
  const upcomingBills = premium?.upcoming_bills ?? [];
  const overspendingAlerts = premium?.overspending_alerts ?? [];
  const spendingPatterns = premium?.spending_patterns ?? [];
  const categoryAnomalies = premium?.category_anomalies ?? [];
  const aiDoItems = Array.isArray(aiAdvice?.what_to_do) ? aiAdvice.what_to_do : [];
  const aiAvoidItems = Array.isArray(aiAdvice?.what_to_avoid) ? aiAdvice.what_to_avoid : [];
  const filteredMerchantMappings = merchantMappings.filter((m) =>
    m.merchant.toLowerCase().includes(merchantSearch.toLowerCase())
  );

  return (
    <div className="finance-bg min-h-screen text-slate-900">
      <div className="mx-auto max-w-[1480px] px-4 py-5 md:px-6 md:py-6">
        <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-emerald-700">Money Command Center</p>
            <h1 className="font-display text-3xl text-slate-900 md:text-4xl">Personal Finance Tracker</h1>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-outline" onClick={openMerchantManager}>
              Merchant Manager
            </button>
            <button className="btn-outline" onClick={() => setDark((v) => !v)}>
              {dark ? "Light UI" : "Dark UI"}
            </button>
          </div>
        </header>

        <div className="mb-4 grid gap-3 md:grid-cols-6">
          <div className="md:col-span-2">
            <input type="file" accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="input w-full" />
          </div>
          <input value={bankName} onChange={(e) => setBankName(e.target.value)} placeholder="Bank name (optional)" className="input" />
          <button className="btn-primary" onClick={onUpload} disabled={loading}>
            {loading ? "Uploading..." : "Upload Statement"}
          </button>
          <a href={exportTransactionsXlsxUrl} className="btn-secondary text-center">
            Export Excel
          </a>
          <a href={exportSummaryPdfUrl} className="btn-secondary text-center">
            Export PDF
          </a>
        </div>

        <div className="mb-4 grid gap-3 md:grid-cols-5">
          <input type="date" value={filters.start} onChange={(e) => setFilters((f) => ({ ...f, start: e.target.value }))} className="input" />
          <input type="date" value={filters.end} onChange={(e) => setFilters((f) => ({ ...f, end: e.target.value }))} className="input" />
          <select value={filters.category} onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))} className="input">
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button className="btn-outline" onClick={loadAll}>
            Refresh
          </button>
          <div className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{message || "Ready"}</div>
        </div>

        <section className="mb-4 grid gap-3 md:grid-cols-5">
          {[
            ["Income", money(dashboard?.totals?.income)],
            ["Expense", money(dashboard?.totals?.expense)],
            ["Savings", money(dashboard?.totals?.savings)],
            ["Savings Rate", `${dashboard?.totals?.savings_rate ?? 0}%`],
            ["Burn Rate", money(dashboard?.totals?.burn_rate)],
          ].map(([label, value]) => (
            <article key={label} className="card-kpi">
              <p className="text-xs uppercase tracking-[0.12em] text-slate-500">{label}</p>
              <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-4 xl:grid-cols-12">
          <Card title="Category Split" className="xl:col-span-3">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={dashboard?.by_category ?? []} dataKey="amount" nameKey="category" outerRadius={92}>
                    {(dashboard?.by_category ?? []).map((entry, index) => (
                      <Cell key={`${entry.category}-${entry.amount}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => money(v)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Cashflow Trend" className="xl:col-span-6">
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={dashboard?.monthly_trend ?? []}>
                  <defs>
                    <linearGradient id="incomeG" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="expenseG" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f97316" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#f97316" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#dbe4ea" />
                  <XAxis dataKey="month" stroke="#64748b" />
                  <YAxis stroke="#64748b" />
                  <Tooltip formatter={(v) => money(v)} />
                  <Area type="monotone" dataKey="income" stroke="#059669" fill="url(#incomeG)" />
                  <Area type="monotone" dataKey="expense" stroke="#ea580c" fill="url(#expenseG)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Forecast" className="xl:col-span-3">
            <div className="space-y-2 text-sm">
              <p className="metric-row">
                Next expense <span>{money(forecast?.monthly_expense_forecast)}</span>
              </p>
              <p className="metric-row">
                Next savings <span>{money(forecast?.monthly_savings_forecast)}</span>
              </p>
              <p className="metric-row">
                Next balance <span>{money(forecast?.next_balance_forecast)}</span>
              </p>
              <p className="mt-3 rounded-lg bg-slate-50 p-2 text-slate-700">
                Health score: <b>{premium?.financial_health_score ?? 0}/100</b>
              </p>
            </div>
          </Card>
        </section>

        <section className="mt-4 grid gap-4 xl:grid-cols-12">
          <Card title="Risk & Alert Center" className="xl:col-span-4">
            <div className="space-y-3 text-sm">
              <div>
                <p className="mb-1 font-medium text-slate-700">Overspending Alerts</p>
                <div className="space-y-2">
                  {overspendingAlerts.slice(0, 4).map((a, idx) => (
                    <p key={`${a.title}-${idx}`} className={`rounded-lg border p-2 ${a.severity === "high" ? "border-rose-200 bg-rose-50 text-rose-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
                      <b>{a.title}</b>
                      <br />
                      {a.message}
                    </p>
                  ))}
                  {!overspendingAlerts.length && <p className="rounded-lg border border-slate-200 bg-slate-50 p-2">No overspending alerts.</p>}
                </div>
              </div>

              <div>
                <p className="mb-1 font-medium text-slate-700">Spending Patterns</p>
                <div className="space-y-2">
                  {spendingPatterns.slice(0, 4).map((p, idx) => (
                    <p key={`${p.pattern}-${idx}`} className="rounded-lg border border-cyan-200 bg-cyan-50 p-2 text-cyan-800">
                      {p.message}
                    </p>
                  ))}
                  {!spendingPatterns.length && <p className="rounded-lg border border-slate-200 bg-slate-50 p-2">Not enough data yet.</p>}
                </div>
              </div>

              <div>
                <p className="mb-1 font-medium text-slate-700">Category Anomalies</p>
                <div className="space-y-2">
                  {categoryAnomalies.slice(0, 4).map((a, idx) => (
                    <p key={`${a.category}-${idx}`} className="rounded-lg border border-fuchsia-200 bg-fuchsia-50 p-2 text-fuchsia-800">
                      <b>{a.category}</b> · {a.change_pct}% above baseline
                    </p>
                  ))}
                  {!categoryAnomalies.length && <p className="rounded-lg border border-slate-200 bg-slate-50 p-2">No anomalies detected.</p>}
                </div>
              </div>
            </div>
          </Card>

          <Card title="Premium Insights" className="xl:col-span-4">
            <div className="space-y-2 text-sm">
              {aiAdvice?.summary && (
                <p className="rounded-lg border border-emerald-200 bg-emerald-50 p-2 text-emerald-900">
                  <b>AI Coach:</b> {aiAdvice.summary}
                </p>
              )}
              {aiDiagnostics && (
                <p
                  className={`rounded-lg border p-2 text-xs ${
                    aiDiagnostics.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"
                  }`}
                >
                  <b>AI Diagnostics:</b> {aiDiagnostics.message}
                  {aiDiagnostics?.checks?.model ? ` (model: ${aiDiagnostics.checks.model})` : ""}
                </p>
              )}
              {aiAdvice?.llm_error && (
                <p className="rounded-lg border border-rose-200 bg-rose-50 p-2 text-rose-800">
                  <b>LLM error:</b> {aiAdvice.llm_error}
                </p>
              )}
              {aiDoItems.slice(0, 3).map((x, idx) => (
                <p key={`do-${idx}`} className="rounded-lg border border-teal-100 bg-teal-50 p-2 text-teal-800">
                  <b>Do:</b> {x.title} — {x.reason}
                </p>
              ))}
              {aiAvoidItems.slice(0, 3).map((x, idx) => (
                <p key={`avoid-${idx}`} className="rounded-lg border border-rose-100 bg-rose-50 p-2 text-rose-800">
                  <b>Avoid:</b> {x.title} — {x.reason}
                </p>
              ))}
              {insights.slice(0, 8).map((i) => (
                <p key={i.id ?? i.content} className="rounded-lg border border-emerald-100 bg-emerald-50 p-2 text-emerald-800">
                  {i.content}
                </p>
              ))}
              {!insights.length && <p className="rounded-lg border border-slate-200 bg-slate-50 p-2">No insights yet.</p>}
            </div>
          </Card>

          <Card title="Upcoming Bills & Top Merchants" className="xl:col-span-4">
            <div className="space-y-3 text-sm">
              <div>
                <p className="mb-1 font-medium text-slate-700">Upcoming Bills</p>
                <div className="space-y-2">
                  {upcomingBills.slice(0, 5).map((r) => (
                    <p key={`${r.merchant}-${r.due_date}`} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                      {r.merchant} · {money(r.expected_amount)} · due in {r.days_left}d
                    </p>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-1 font-medium text-slate-700">Top Merchants</p>
                <div className="space-y-2">
                  {topMerchants.slice(0, 5).map((m) => (
                    <p key={m.merchant} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                      {m.merchant} · {money(m.spend)}
                    </p>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        </section>

        <section className="mt-4 grid gap-4 xl:grid-cols-12">
          <Card title="Transaction Explorer" className="xl:col-span-7">
            <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr>
                    <th className="p-2">
                      <button type="button" className="font-semibold text-slate-700 hover:text-slate-900" onClick={() => toggleTxnSort("txn_date")}>
                        {sortLabel("txn_date", "Date")}
                      </button>
                    </th>
                    <th className="p-2">
                      <button type="button" className="font-semibold text-slate-700 hover:text-slate-900" onClick={() => toggleTxnSort("merchant")}>
                        {sortLabel("merchant", "Merchant")}
                      </button>
                    </th>
                    <th className="p-2">
                      <button type="button" className="font-semibold text-slate-700 hover:text-slate-900" onClick={() => toggleTxnSort("amount")}>
                        {sortLabel("amount", "Amount")}
                      </button>
                    </th>
                    <th className="p-2">
                      <button type="button" className="font-semibold text-slate-700 hover:text-slate-900" onClick={() => toggleTxnSort("category")}>
                        {sortLabel("category", "Category")}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedTransactions.map((t) => (
                    <tr key={t.id} className="border-b border-slate-100">
                      <td className="p-2">{t.txn_date}</td>
                      <td className="p-2">{t.merchant}</td>
                      <td className={`p-2 font-medium ${t.amount < 0 ? "text-rose-600" : "text-emerald-700"}`}>{money(t.amount)}</td>
                      <td className="p-2">
                        <select value={t.category} onChange={(e) => onUpdateCategory(t.id, e.target.value, t.merchant)} className="input h-8 py-1">
                          {categories.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Budgets" className="xl:col-span-2">
            <div className="space-y-2">
              <select value={budgetForm.category} onChange={(e) => setBudgetForm((f) => ({ ...f, category: e.target.value }))} className="input w-full">
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
              <input type="number" value={budgetForm.amount} onChange={(e) => setBudgetForm((f) => ({ ...f, amount: e.target.value }))} placeholder="Budget amount" className="input w-full" />
              <input type="month" value={budgetForm.month} onChange={(e) => setBudgetForm((f) => ({ ...f, month: e.target.value }))} className="input w-full" />
              <button onClick={onSaveBudget} className="btn-primary w-full">
                Save
              </button>
            </div>
            <div className="mt-3 space-y-2 text-sm">
              {budgets.map((b) => (
                <p key={b.id} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                  {b.category} · {money(b.amount)}
                </p>
              ))}
            </div>
          </Card>

          <Card title="Budget Health" className="xl:col-span-3">
            <div className="space-y-2 text-sm">
              {budgetStatus.map((b) => (
                <div key={b.category} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                  <p className="font-medium">{b.category}</p>
                  <p className="text-slate-600">
                    {money(b.spent)} / {money(b.budget)} · {b.usage_pct}%
                  </p>
                  <p className={`${b.status === "over" ? "text-rose-600" : b.status === "near" ? "text-amber-600" : "text-emerald-600"}`}>
                    {b.status.toUpperCase()}
                  </p>
                </div>
              ))}
            </div>
          </Card>
        </section>

        <section className="mt-4">
          <Card title="Goals & Milestones">
            <div className="mb-3 grid gap-2 md:grid-cols-5">
              <input value={goalForm.title} onChange={(e) => setGoalForm((f) => ({ ...f, title: e.target.value }))} placeholder="Goal title" className="input" />
              <input type="number" value={goalForm.target_amount} onChange={(e) => setGoalForm((f) => ({ ...f, target_amount: e.target.value }))} placeholder="Target amount" className="input" />
              <input type="number" value={goalForm.current_amount} onChange={(e) => setGoalForm((f) => ({ ...f, current_amount: e.target.value }))} placeholder="Current amount" className="input" />
              <input type="date" value={goalForm.target_date} onChange={(e) => setGoalForm((f) => ({ ...f, target_date: e.target.value }))} className="input" />
              <button onClick={onCreateGoal} className="btn-primary">
                Add Goal
              </button>
            </div>
            <div className="grid gap-2 md:grid-cols-3">
              {goals.slice(0, 9).map((g) => {
                const pct = Math.min(100, Math.round(((g.current_amount || 0) / (g.target_amount || 1)) * 100));
                return (
                  <article key={g.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <p className="font-medium text-slate-800">{g.title}</p>
                    <p className="text-sm text-slate-600">
                      {money(g.current_amount)} / {money(g.target_amount)} · {pct}%
                    </p>
                    <div className="mt-2 h-2 rounded bg-slate-200">
                      <div className="h-2 rounded bg-emerald-600" style={{ width: `${pct}%` }} />
                    </div>
                    <button className="mt-2 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700" onClick={() => onAddGoalProgress(g.id, g.current_amount)}>
                      Update Progress
                    </button>
                  </article>
                );
              })}
            </div>
          </Card>
        </section>

        {merchantModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
            <div className="card-surface max-h-[88vh] w-full max-w-5xl overflow-hidden">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="font-display text-2xl text-slate-900">Merchant Category Manager</h3>
                <button className="btn-outline" onClick={() => setMerchantModalOpen(false)}>
                  Close
                </button>
              </div>

              <div className="mb-3 grid gap-2 md:grid-cols-3">
                <input className="input" placeholder="Search merchant..." value={merchantSearch} onChange={(e) => setMerchantSearch(e.target.value)} />
                <input className="input" placeholder="Add custom category" value={customCategory} onChange={(e) => setCustomCategory(e.target.value)} />
                <button className="btn-primary" onClick={addCustomCategory}>
                  Add Category
                </button>
              </div>

              <div className="max-h-[54vh] overflow-auto rounded-xl border border-slate-200">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-white">
                    <tr>
                      <th className="p-2">Merchant</th>
                      <th className="p-2">Txn Count</th>
                      <th className="p-2">Category</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMerchantMappings.map((m) => (
                      <tr key={m.merchant} className="border-b border-slate-100">
                        <td className="p-2">{m.merchant}</td>
                        <td className="p-2">{m.count}</td>
                        <td className="p-2">
                          <select
                            className="input h-8 py-1"
                            value={merchantDraft[m.merchant] ?? ""}
                            onChange={(e) =>
                              setMerchantDraft((prev) => ({
                                ...prev,
                                [m.merchant]: e.target.value,
                              }))
                            }
                          >
                            <option value="">Select category</option>
                            {categories.map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex justify-end gap-2">
                <button className="btn-outline" onClick={() => setMerchantModalOpen(false)}>
                  Cancel
                </button>
                <button className="btn-primary" onClick={saveMerchantMappings}>
                  Apply to All Transactions
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
