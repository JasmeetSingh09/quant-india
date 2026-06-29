import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { calcSIP, calcLumpsum, calcTax } from '../api'
import { Calculator } from 'lucide-react'

// Compact Indian formatting so big numbers don't overflow the cards
const fmt = (n) => {
  n = Number(n)
  const a = Math.abs(n)
  if (a >= 1e7) return '₹' + (n / 1e7).toFixed(2) + ' Cr'
  if (a >= 1e5) return '₹' + (n / 1e5).toFixed(2) + ' L'
  return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

function Field({ label, value, onChange, suffix }) {
  return (
    <div>
      <label className="label">{label}</label>
      <div className="relative">
        <input className="input" type="number" value={value} onChange={e=>onChange(e.target.value)} />
        {suffix && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">{suffix}</span>}
      </div>
    </div>
  )
}

export default function Calculators() {
  const [tab, setTab] = useState('sip')

  // SIP
  const [sip, setSip] = useState({ monthly_investment: 5000, annual_return_pct: 12, years: 10 })
  const sipMut = useMutation({ mutationFn: calcSIP })
  // Lumpsum
  const [lump, setLump] = useState({ principal: 100000, annual_return_pct: 12, years: 10 })
  const lumpMut = useMutation({ mutationFn: calcLumpsum })
  // Tax
  const [tax, setTax] = useState({ buy_price: 100, sell_price: 150, quantity: 100, holding_months: 18 })
  const taxMut = useMutation({ mutationFn: calcTax })

  const tabs = [['sip','SIP'],['lumpsum','Lumpsum'],['tax','Capital Gains Tax']]

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><Calculator size={24} className="text-green-400"/> Calculators</h1>
        <p className="text-gray-400 text-sm mt-0.5">Plan your investing — SIP, lumpsum, and Indian capital-gains tax.</p>
      </div>

      <div className="flex bg-gray-800 rounded-lg p-1 w-fit">
        {tabs.map(([v,l])=>(
          <button key={v} onClick={()=>setTab(v)}
            className={`px-4 py-1.5 rounded text-sm font-medium ${tab===v?'bg-green-600 text-white':'text-gray-400 hover:text-gray-200'}`}>{l}</button>
        ))}
      </div>

      {/* SIP */}
      {tab==='sip' && (
        <div className="card space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Monthly investment" value={sip.monthly_investment} onChange={v=>setSip(s=>({...s,monthly_investment:v}))} suffix="₹" />
            <Field label="Expected return" value={sip.annual_return_pct} onChange={v=>setSip(s=>({...s,annual_return_pct:v}))} suffix="%/yr" />
            <Field label="Duration" value={sip.years} onChange={v=>setSip(s=>({...s,years:v}))} suffix="yrs" />
          </div>
          <button className="btn-primary" onClick={()=>sipMut.mutate({...sip, monthly_investment:Number(sip.monthly_investment), annual_return_pct:Number(sip.annual_return_pct), years:Number(sip.years)})}>Calculate</button>
          {sipMut.data && !sipMut.data.error && (
            <div className="grid grid-cols-3 gap-3 pt-2">
              <div className="card-sm"><p className="stat-label">You invest</p><p className="stat-value">{fmt(sipMut.data.total_invested)}</p></div>
              <div className="card-sm"><p className="stat-label">Future value</p><p className="stat-value positive">{fmt(sipMut.data.future_value)}</p></div>
              <div className="card-sm"><p className="stat-label">Gains</p><p className="stat-value positive">{fmt(sipMut.data.estimated_gains)}</p></div>
              <p className="text-xs text-gray-400 col-span-3">{sipMut.data.interpretation}</p>
            </div>
          )}
          {sipMut.isError && <p className="text-red-400 text-xs">{String(sipMut.error)}</p>}
        </div>
      )}

      {/* Lumpsum */}
      {tab==='lumpsum' && (
        <div className="card space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Amount" value={lump.principal} onChange={v=>setLump(s=>({...s,principal:v}))} suffix="₹" />
            <Field label="Expected return" value={lump.annual_return_pct} onChange={v=>setLump(s=>({...s,annual_return_pct:v}))} suffix="%/yr" />
            <Field label="Duration" value={lump.years} onChange={v=>setLump(s=>({...s,years:v}))} suffix="yrs" />
          </div>
          <button className="btn-primary" onClick={()=>lumpMut.mutate({...lump, principal:Number(lump.principal), annual_return_pct:Number(lump.annual_return_pct), years:Number(lump.years)})}>Calculate</button>
          {lumpMut.data && !lumpMut.data.error && (
            <div className="grid grid-cols-2 gap-3 pt-2">
              <div className="card-sm"><p className="stat-label">Future value</p><p className="stat-value positive">{fmt(lumpMut.data.future_value)}</p></div>
              <div className="card-sm"><p className="stat-label">Gains</p><p className="stat-value positive">{fmt(lumpMut.data.estimated_gains)}</p></div>
              <p className="text-xs text-gray-400 col-span-2">{lumpMut.data.interpretation}</p>
            </div>
          )}
        </div>
      )}

      {/* Tax */}
      {tab==='tax' && (
        <div className="card space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <Field label="Buy price" value={tax.buy_price} onChange={v=>setTax(s=>({...s,buy_price:v}))} suffix="₹" />
            <Field label="Sell price" value={tax.sell_price} onChange={v=>setTax(s=>({...s,sell_price:v}))} suffix="₹" />
            <Field label="Quantity" value={tax.quantity} onChange={v=>setTax(s=>({...s,quantity:v}))} />
            <Field label="Held for" value={tax.holding_months} onChange={v=>setTax(s=>({...s,holding_months:v}))} suffix="mo" />
          </div>
          <button className="btn-primary" onClick={()=>taxMut.mutate({buy_price:Number(tax.buy_price), sell_price:Number(tax.sell_price), quantity:Number(tax.quantity), holding_months:Number(tax.holding_months)})}>Calculate Tax</button>
          {taxMut.data && !taxMut.data.error && (
            <div className="space-y-3 pt-2">
              <div className="grid grid-cols-4 gap-3">
                <div className="card-sm"><p className="stat-label">Gain</p><p className={`stat-value ${taxMut.data.gain>=0?'positive':'negative'}`}>{fmt(taxMut.data.gain)}</p></div>
                <div className="card-sm"><p className="stat-label">Term</p><p className="stat-value capitalize">{taxMut.data.term}</p></div>
                <div className="card-sm"><p className="stat-label">Tax</p><p className="stat-value negative">{fmt(taxMut.data.tax)}</p></div>
                <div className="card-sm"><p className="stat-label">Net profit</p><p className="stat-value positive">{fmt(taxMut.data.net_profit)}</p></div>
              </div>
              <p className="text-xs text-gray-400">{taxMut.data.note}</p>
              <p className="text-[11px] text-gray-600">Post-July-2024 rules: STCG 20%, LTCG 12.5% above ₹1.25L. Estimate only — not tax advice.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
