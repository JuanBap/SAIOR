/** Genera y descarga un PDF a partir de un nodo del DOM, sin diálogo de impresión.
 *  Usa html2canvas-pro (soporta los colores oklch del tema) + jsPDF. Fuerza el
 *  render en claro para que el PDF sea legible aunque la app esté en modo oscuro. */
export async function downloadElementPdf(el: HTMLElement | null, filename: string): Promise<void> {
  if (!el) return;
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([
    import("html2canvas-pro"),
    import("jspdf"),
  ]);

  // Escala adaptativa: nodos muy altos (reporte de insights) bajan a 1.5 para
  // no generar un canvas gigantesco; respuestas del chat van a 2 para nitidez.
  const scale = el.scrollHeight > 2200 ? 1.5 : 2;

  const canvas = await html2canvas(el, {
    backgroundColor: "#ffffff",
    scale,
    useCORS: true,
    // Excluye botones/acciones marcados (no deben salir en el PDF)
    ignoreElements: (node) => (node as HTMLElement).dataset?.noPdf === "true",
    // Render en claro: en el clon quitamos la clase dark para que las variables
    // CSS resuelvan a sus valores claros.
    onclone: (doc) => {
      doc.documentElement.classList.remove("dark");
      doc.documentElement.style.colorScheme = "light";
    },
  });

  const pdf = new jsPDF("p", "mm", "a4");
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const imgW = pageW;
  const imgH = (canvas.height * imgW) / canvas.width;
  // JPEG en vez de PNG: el PNG sin pérdida hace que un render a 2x pese decenas de MB.
  const img = canvas.toDataURL("image/jpeg", 0.92);

  let heightLeft = imgH;
  let position = 0;
  pdf.addImage(img, "JPEG", 0, position, imgW, imgH);
  heightLeft -= pageH;
  while (heightLeft > 0) {
    position -= pageH;
    pdf.addPage();
    pdf.addImage(img, "JPEG", 0, position, imgW, imgH);
    heightLeft -= pageH;
  }
  pdf.save(filename.endsWith(".pdf") ? filename : `${filename}.pdf`);
}
