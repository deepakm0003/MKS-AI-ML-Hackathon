/**
 * Minimal PDF writer (no dependencies): A4 pages, filled / rounded rectangles, lines, real
 * selectable text in the standard Helvetica fonts (WinAnsi encoding) and JPEG images.
 * Coordinates are in points from the TOP-LEFT corner; text y is the baseline.
 */

// Helvetica / Helvetica-Bold advance widths (1/1000 em) for ASCII 32..126 (Adobe AFM)
const W_REG = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
  556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556,
  833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556,
  556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260,
  334, 584];
const W_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
  556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611,
  833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611,
  556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280,
  389, 584];
// WinAnsi code points for the non-ASCII characters the dashboard uses, and their widths
const WIN: Record<string, [number, number]> = {
  "–": [0x96, 556], "—": [0x97, 1000], "·": [0xb7, 278], "×": [0xd7, 584], "’": [0x92, 222], "‘": [0x91, 222],
  "“": [0x93, 333], "”": [0x94, 333], "•": [0x95, 350], "…": [0x85, 1000], "€": [0x80, 556], "°": [0xb0, 400], "±": [0xb1, 584],
};
const SUBST: Record<string, string> = { "→": "->", "←": "<-", "≤": "<=", "≥": ">=", "−": "-", "✓": "OK", "≈": "~", " ": " " };

function encode(s: string): number[] {
  const out: number[] = [];
  for (const ch of s) {
    if (SUBST[ch]) { out.push(...encode(SUBST[ch])); continue; }
    const c = ch.codePointAt(0)!;
    if (c >= 32 && c < 127) out.push(c);
    else if (WIN[ch]) out.push(WIN[ch][0]);
    else if (c >= 160 && c <= 255) out.push(c);
    else out.push(63);                                   // '?'
  }
  return out;
}

const WIDTH_BY_CODE = new Map(Object.values(WIN).map(([code, w]) => [code, w]));
export function textWidth(s: string, size: number, bold = false): number {
  const table = bold ? W_BOLD : W_REG;
  return encode(s).reduce((t, c) => t + (c >= 32 && c < 127 ? table[c - 32] : WIDTH_BY_CODE.get(c) ?? 556), 0) * size / 1000;
}

const esc = (bytes: number[]) => bytes.map((b) => (b === 40 || b === 41 || b === 92 ? `\\${String.fromCharCode(b)}`
  : b < 32 || b > 126 ? `\\${b.toString(8).padStart(3, "0")}` : String.fromCharCode(b))).join("");

function rgb(hex: string): string {
  const h = hex.replace("#", "");
  const n = (i: number) => (parseInt(h.slice(i, i + 2), 16) / 255).toFixed(3);
  return `${n(0)} ${n(2)} ${n(4)}`;
}
const f = (v: number) => (Math.round(v * 100) / 100).toString();

export interface TextOpts { size?: number; bold?: boolean; color?: string; align?: "left" | "right" | "center"; maxWidth?: number }

interface Img { bytes: Uint8Array; w: number; h: number }

export class Pdf {
  readonly W = 595.28;
  readonly H = 841.89;
  private pages: { ops: string[]; imgs: number[] }[] = [];
  private images: Img[] = [];
  private idx = -1;

  get pageCount() { return this.pages.length; }
  private get cur() { return this.pages[this.idx]; }

  addPage(background?: string): void {
    this.pages.push({ ops: [], imgs: [] });
    this.idx = this.pages.length - 1;
    if (background) this.rect(0, 0, this.W, this.H, background);
  }

  /** Draw on an earlier page (e.g. footers once the page count is known). */
  setPage(i: number): void { this.idx = i; }

  rect(x: number, y: number, w: number, h: number, fill: string, opts: { r?: number; stroke?: string; lineWidth?: number } = {}): void {
    const Y = this.H - y - h;
    const path = opts.r ? this.round(x, Y, w, h, Math.min(opts.r, w / 2, h / 2)) : `${f(x)} ${f(Y)} ${f(w)} ${f(h)} re`;
    const paint = opts.stroke ? `${rgb(opts.stroke)} RG ${f(opts.lineWidth ?? 0.75)} w ${fill === "none" ? "S" : "B"}` : "f";
    this.cur.ops.push(`${fill !== "none" ? `${rgb(fill)} rg ` : ""}${path} ${paint}`);
  }

  private round(x: number, y: number, w: number, h: number, r: number): string {
    const k = r * 0.5523;
    return [`${f(x + r)} ${f(y)} m`, `${f(x + w - r)} ${f(y)} l`, `${f(x + w - r + k)} ${f(y)} ${f(x + w)} ${f(y + r - k)} ${f(x + w)} ${f(y + r)} c`,
      `${f(x + w)} ${f(y + h - r)} l`, `${f(x + w)} ${f(y + h - r + k)} ${f(x + w - r + k)} ${f(y + h)} ${f(x + w - r)} ${f(y + h)} c`,
      `${f(x + r)} ${f(y + h)} l`, `${f(x + r - k)} ${f(y + h)} ${f(x)} ${f(y + h - r + k)} ${f(x)} ${f(y + h - r)} c`,
      `${f(x)} ${f(y + r)} l`, `${f(x)} ${f(y + r - k)} ${f(x + r - k)} ${f(y)} ${f(x + r)} ${f(y)} c`, "h"].join(" ");
  }

  line(x1: number, y1: number, x2: number, y2: number, color: string, width = 0.75): void {
    this.cur.ops.push(`${rgb(color)} RG ${f(width)} w ${f(x1)} ${f(this.H - y1)} m ${f(x2)} ${f(this.H - y2)} l S`);
  }

  /** Single line of text; truncated with an ellipsis to maxWidth. Returns the drawn width. */
  text(s: string, x: number, y: number, o: TextOpts = {}): number {
    const size = o.size ?? 10;
    let str = s;
    if (o.maxWidth && textWidth(str, size, o.bold) > o.maxWidth) {
      while (str.length > 1 && textWidth(`${str}…`, size, o.bold) > o.maxWidth) str = str.slice(0, -1);
      str = `${str.trimEnd()}…`;
    }
    const w = textWidth(str, size, o.bold);
    const X = o.align === "right" ? x - w : o.align === "center" ? x - w / 2 : x;
    this.cur.ops.push(`BT /${o.bold ? "F2" : "F1"} ${f(size)} Tf ${rgb(o.color ?? "#ffffff")} rg ${f(X)} ${f(this.H - y)} Td (${esc(encode(str))}) Tj ET`);
    return w;
  }

  /** Word-wrapped lines for a width. */
  wrap(s: string, maxWidth: number, size = 10, bold = false): string[] {
    const lines: string[] = [];
    let line = "";
    for (const word of s.split(/\s+/).filter(Boolean)) {
      const next = line ? `${line} ${word}` : word;
      if (textWidth(next, size, bold) <= maxWidth || !line) line = next;
      else { lines.push(line); line = word; }
    }
    if (line) lines.push(line);
    return lines;
  }

  /** Paragraph; returns the y below the last line. */
  paragraph(s: string, x: number, y: number, maxWidth: number, o: TextOpts & { lineHeight?: number } = {}): number {
    const size = o.size ?? 10;
    const lh = o.lineHeight ?? size * 1.4;
    let yy = y;
    for (const l of this.wrap(s, maxWidth, size, o.bold)) { this.text(l, x, yy, { ...o, maxWidth: undefined }); yy += lh; }
    return yy;
  }

  /** JPEG from a data URL (image/jpeg), drawn at x, y with size w x h points. */
  image(dataUrl: string, px: { w: number; h: number }, x: number, y: number, w: number, h: number): void {
    const b64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    this.images.push({ bytes, w: px.w, h: px.h });
    const id = this.images.length;
    this.cur.imgs.push(id);
    this.cur.ops.push(`q ${f(w)} 0 0 ${f(h)} ${f(x)} ${f(this.H - y - h)} cm /Im${id} Do Q`);
  }

  toBlob(meta: { title?: string; author?: string } = {}): Blob {
    const enc = new TextEncoder();
    const parts: Uint8Array[] = [];
    const offsets: number[] = [];
    let pos = 0;
    const push = (p: Uint8Array | string) => { const b = typeof p === "string" ? enc.encode(p) : p; parts.push(b); pos += b.length; };
    const nImg = this.images.length;
    const nPages = this.pages.length;
    // object numbers: 1 catalog, 2 pages, 3 F1, 4 F2, 5 info, then images, then (content, page) per page
    const imgObj = (i: number) => 5 + i;                       // i is 1-based
    const contentObj = (p: number) => 6 + nImg + p * 2;
    const pageObj = (p: number) => 7 + nImg + p * 2;
    const obj = (n: number, body: string | Uint8Array[]) => {
      offsets[n] = pos;
      push(`${n} 0 obj\n`);
      if (typeof body === "string") push(body);
      else body.forEach(push);
      push("\nendobj\n");
    };
    push("%PDF-1.4\n%âãÏÓ\n");
    obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
    obj(2, `<< /Type /Pages /Count ${nPages} /Kids [${this.pages.map((_, p) => `${pageObj(p)} 0 R`).join(" ")}] >>`);
    obj(3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>");
    obj(4, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>");
    const pdfStr = (s: string) => `(${esc(encode(s))})`;
    obj(5, `<< /Title ${pdfStr(meta.title ?? "Report")} /Author ${pdfStr(meta.author ?? "Celeris Control Tower")} /Producer (Celeris dashboard) >>`);
    this.images.forEach((im, i) => obj(imgObj(i + 1), [
      enc.encode(`<< /Type /XObject /Subtype /Image /Width ${im.w} /Height ${im.h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${im.bytes.length} >>\nstream\n`),
      im.bytes, enc.encode("\nendstream")]));
    this.pages.forEach((pg, p) => {
      const content = pg.ops.join("\n");
      obj(contentObj(p), `<< /Length ${enc.encode(content).length} >>\nstream\n${content}\nendstream`);
      const xo = pg.imgs.length ? `/XObject << ${pg.imgs.map((i) => `/Im${i} ${imgObj(i)} 0 R`).join(" ")} >>` : "";
      obj(pageObj(p), `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${f(this.W)} ${f(this.H)}] ` +
        `/Resources << /Font << /F1 3 0 R /F2 4 0 R >> ${xo} >> /Contents ${contentObj(p)} 0 R >>`);
    });
    const total = 5 + nImg + nPages * 2;
    const xref = pos;
    push(`xref\n0 ${total + 1}\n0000000000 65535 f \n`);
    for (let n = 1; n <= total; n++) push(`${String(offsets[n]).padStart(10, "0")} 00000 n \n`);
    push(`trailer\n<< /Size ${total + 1} /Root 1 0 R /Info 5 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
    return new Blob(parts, { type: "application/pdf" });
  }
}
