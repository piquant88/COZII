// Cozii currency helper
export type CurrencyInfo = { code: string; symbol: string; name: string; locale?: string };

export const CURRENCIES: CurrencyInfo[] = [
  { code: 'USD', symbol: '$',  name: 'US Dollar',           locale: 'en-US' },
  { code: 'CAD', symbol: 'C$', name: 'Canadian Dollar',     locale: 'en-CA' },
  { code: 'EUR', symbol: '€',  name: 'Euro',                 locale: 'en-IE' },
  { code: 'GBP', symbol: '£',  name: 'British Pound',        locale: 'en-GB' },
  { code: 'IDR', symbol: 'Rp', name: 'Indonesian Rupiah',    locale: 'id-ID' },
  { code: 'INR', symbol: '₹',  name: 'Indian Rupee',         locale: 'en-IN' },
  { code: 'AUD', symbol: 'A$', name: 'Australian Dollar',    locale: 'en-AU' },
  { code: 'JPY', symbol: '¥',  name: 'Japanese Yen',         locale: 'ja-JP' },
  { code: 'SGD', symbol: 'S$', name: 'Singapore Dollar',     locale: 'en-SG' },
  { code: 'MYR', symbol: 'RM', name: 'Malaysian Ringgit',    locale: 'ms-MY' },
  { code: 'AED', symbol: 'AED',name: 'UAE Dirham',           locale: 'en-AE' },
  { code: 'MXN', symbol: 'MX$',name: 'Mexican Peso',         locale: 'es-MX' },
  { code: 'BRL', symbol: 'R$', name: 'Brazilian Real',       locale: 'pt-BR' },
  { code: 'ZAR', symbol: 'R',  name: 'South African Rand',   locale: 'en-ZA' },
  { code: 'CNY', symbol: '¥',  name: 'Chinese Yuan',         locale: 'zh-CN' },
];

export function getCurrency(code?: string | null): CurrencyInfo {
  const c = (code || 'USD').toUpperCase();
  return CURRENCIES.find((x) => x.code === c) || { code: c, symbol: c, name: c };
}

export function formatMoney(amount: number, code?: string | null): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) amount = 0;
  const cur = getCurrency(code);
  const noDecimals = cur.code === 'JPY' || cur.code === 'IDR' || cur.code === 'KRW' || cur.code === 'VND';
  try {
    return new Intl.NumberFormat(cur.locale || 'en-US', {
      style: 'currency',
      currency: cur.code,
      minimumFractionDigits: noDecimals ? 0 : 2,
      maximumFractionDigits: noDecimals ? 0 : 2,
      currencyDisplay: 'symbol',
    }).format(amount);
  } catch {
    // Fallback if currency code isn't recognised by Intl
    const fixed = noDecimals ? Math.round(amount).toLocaleString() : amount.toFixed(2);
    return `${cur.symbol}${fixed}`;
  }
}

export function formatCompact(amount: number, code?: string | null): string {
  const cur = getCurrency(code);
  if (Math.abs(amount) >= 1000) {
    return `${cur.symbol}${(amount / 1000).toFixed(1)}k`;
  }
  return formatMoney(amount, code);
}

// Plain-English tax/spending tips. NOT legal advice – just a friendly nudge.
export function taxTips(code?: string | null): string[] {
  const c = (code || 'USD').toUpperCase();
  const map: Record<string, string[]> = {
    USD: [
      'US sales tax varies by state (0–10%). Your receipt total already includes it — enter the total you actually paid.',
      'Tipping in the US is typically 15–20% at restaurants, 10–15% for delivery, and is rarely included.',
      'Track grocery vs. dining-out separately so it is easier to spot food-cost creep.',
    ],
    CAD: [
      'Canada has GST (5%) plus provincial PST/HST. In Ontario it is HST 13%; in BC it is GST 5% + PST 7%; Alberta is just GST 5%.',
      'Tipping at restaurants is 15–20%; coffee shops a tip jar is enough.',
      'Splitting rent? Heat/hydro often vary month-to-month — use Recurring Bills so the variable amount is captured each time you pay.',
    ],
    IDR: [
      'Indonesia charges PPN (VAT) 11% on most goods. Restaurants often add 10% PB1 (service tax) plus 5–10% service charge.',
      'Tipping is not mandatory but rounding up or 5–10% for great service is appreciated.',
      'Compare your home spending in IDR to your overseas spending separately by switching the space currency.',
    ],
    INR: [
      'India uses GST: most goods are 5–18%, eating-out is 5–18% (depending on restaurant type).',
      'Tipping at restaurants is usually 5–10%; a service charge may already be on the bill.',
      'Track utilities (electricity, water, internet) as Recurring Bills — monthly billing dates differ.',
    ],
    GBP: [
      'UK VAT is 20% on most things; food groceries are usually zero-rated, but ready-meals and dine-in are taxable.',
      'Tipping 10–15% if service charge is not already added; check the bill.',
      'Council tax is usually a separate monthly bill — add it to Recurring Bills.',
    ],
    EUR: [
      'EU VAT is country-specific: Germany 19%, France 20%, Spain 21%, Ireland 23% — already in your receipt total.',
      'Tipping is modest: 5–10% at restaurants, often optional.',
    ],
    AUD: [
      'Australia has GST 10% on most goods; tipping is uncommon but appreciated for great service.',
    ],
    MYR: [
      'Malaysia has SST (sales 5–10%, service 6%). Restaurants often add 6% service tax + 10% service charge.',
    ],
    SGD: [
      'Singapore GST is 9%. Restaurants typically add 10% service charge plus 9% GST on the subtotal.',
    ],
    JPY: [
      'Japan has consumption tax 10% (8% on take-away food). Tipping is generally not expected.',
    ],
    AED: ['UAE VAT is 5%. Service charge may already be added at restaurants.'],
    MXN: ['Mexico IVA is 16%; tipping 10–15% is standard at restaurants.'],
    BRL: ['Brazilian taxes are bundled (ICMS varies by state). Restaurants often add 10% service.'],
    ZAR: ['South Africa VAT is 15%; tipping ~10% at restaurants.'],
    CNY: ['China VAT is typically 13% on goods; tipping is uncommon.'],
  };
  return map[c] || ['Pick a currency that matches where you spend the most so reports stay meaningful. Switch anytime in Profile.'];
}
