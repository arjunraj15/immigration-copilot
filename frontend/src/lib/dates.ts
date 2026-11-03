// The one place dates are turned into text for the screen. Every date is shown in US format, MM/DD/YYYY.
// Display only. The backend does all date math and sends YYYY-MM-DD or an ISO timestamp. A date a document wrote in
// another style, in words, year first or with dots, is turned into the same format. One that reads two ways, such as
// 03/04/2025, is shown as it came because guessing the order would change what the document says.

const TIME = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const ORDINAL = /(?<=\d)(st|nd|rd|th)\b/gi;
const YMD = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/;
const PARTS = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/;
const DAY_FIRST_WORDS = /^(\d{1,2})[ -]([A-Za-z]{3,9})\.?,?[ -]?(\d{4})$/;
const MONTH_FIRST_WORDS = /^([A-Za-z]{3,9})\.? (\d{1,2}),? ?(\d{4})$/;

const two = (n: number) => String(n).padStart(2, "0");

// The text for a real calendar date, or null when the numbers are not one.
function make(year: number, month: number, day: number): string | null {
  const when = new Date(year, month - 1, day);
  const real = when.getFullYear() === year && when.getMonth() === month - 1 && when.getDate() === day;
  return real ? `${two(month)}/${two(day)}/${year}` : null;
}

function monthOf(word: string): number {
  return MONTHS.indexOf(word.slice(0, 3).toLowerCase()) + 1;
}

// The date a text reads as, in US format, or null when it is not one date written one way.
function read(text: string): string | null {
  const clean = text.replace(ORDINAL, "").replace(/\bsept\b/i, "Sep").trim();
  let m = YMD.exec(clean);
  if (m) return make(Number(m[1]), Number(m[2]), Number(m[3]));
  m = DAY_FIRST_WORDS.exec(clean);
  if (m && monthOf(m[2])) return make(Number(m[3]), monthOf(m[2]), Number(m[1]));
  m = MONTH_FIRST_WORDS.exec(clean);
  if (m && monthOf(m[1])) return make(Number(m[3]), monthOf(m[1]), Number(m[2]));
  m = PARTS.exec(clean);
  if (m) {
    const [first, second, year] = [Number(m[1]), Number(m[2]), Number(m[3])];
    if (first > 12 && second <= 12) return make(year, second, first); // only one way to read it
    if (second > 12 && first <= 12) return make(year, first, second);
    if (first === second) return make(year, first, second);
  }
  return null;
}

// A date as MM/DD/YYYY. A YYYY-MM-DD value is cut up as text, so a time zone cannot shift the day.
// A full ISO timestamp shows the day the viewer's clock gives it. Anything else, empty or unreadable, is shown as it came.
export function usDate(value: string | null | undefined): string {
  const text = (value ?? "").trim();
  if (/^\d{4}-\d{2}-\d{2}T/.test(text)) {
    const when = new Date(text);
    return Number.isNaN(when.getTime()) ? text : `${two(when.getMonth() + 1)}/${two(when.getDate())}/${when.getFullYear()}`;
  }
  return read(text) ?? value ?? "";
}

// A timestamp as MM/DD/YYYY, 2:30 PM.
export function usDateTime(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : `${usDate(iso)}, ${TIME.format(when)}`;
}

// A clock time as 2:30 PM.
export function usTime(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : TIME.format(when);
}
