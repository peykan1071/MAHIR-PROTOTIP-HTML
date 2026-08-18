(() => {
  const encoder = new TextEncoder();

  const getCommon = () => {
    if (!window.MAHIRReportExport) throw new Error("Ortak rapor çıktı modeli yüklenemedi.");
    return window.MAHIRReportExport;
  };

  const setFont = (context, size, weight = 400) => {
    context.font = `${weight} ${size}px Arial, "Segoe UI", sans-serif`;
  };

  const wrapText = (context, text, maxWidth) => {
    const lines = [];
    String(text || "").split(/\r?\n/).forEach((rawLine) => {
      const words = rawLine.replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
      let line = "";
      words.forEach((word) => {
        const candidate = line ? `${line} ${word}` : word;
        if (context.measureText(candidate).width <= maxWidth) {
          line = candidate;
          return;
        }
        if (line) lines.push(line);
        if (context.measureText(word).width <= maxWidth) {
          line = word;
          return;
        }
        let chunk = "";
        [...word].forEach((char) => {
          const candidateChunk = chunk + char;
          if (context.measureText(candidateChunk).width <= maxWidth) {
            chunk = candidateChunk;
          } else {
            if (chunk) lines.push(chunk);
            chunk = char;
          }
        });
        line = chunk;
      });
      if (line) lines.push(line);
      if (!words.length) lines.push("");
    });
    return lines.length ? lines : [""];
  };

  const drawLines = (context, lines, x, y, lineHeight) => {
    lines.forEach((line, index) => context.fillText(line, x, y + index * lineHeight));
    return y + lines.length * lineHeight;
  };

  const normalizeColumnWidths = (weights, columnCount, width) => {
    const normalized = Array.isArray(weights) && weights.length === columnCount
      ? weights.map((value) => Math.max(Number(value) || 0, 0))
      : Array.from({ length: columnCount }, () => 1);
    const total = normalized.reduce((sum, value) => sum + value, 0) || columnCount;
    let allocated = 0;
    return normalized.map((value, index) => {
      const columnWidth = index === columnCount - 1 ? width - allocated : width * value / total;
      allocated += columnWidth;
      return columnWidth;
    });
  };

  const measureTable = (context, table, width, design, weights = null) => {
    const columnCount = Math.max(...table.map((row) => row.length), 1);
    const columnWidths = normalizeColumnWidths(weights, columnCount, width);
    const rowLayouts = table.map((row, rowIndex) => {
      const cells = Array.from({ length: columnCount }, (_, index) => {
        setFont(context, design.tableSize, rowIndex === 0 || (index === 0 && columnCount === 2) ? 800 : 400);
        const lines = wrapText(context, row[index] || "", columnWidths[index] - design.tableCellPaddingX * 2);
        return { lines, header: rowIndex === 0, label: index === 0 && columnCount === 2 };
      });
      const height = Math.max(21, Math.max(...cells.map((cell) => cell.lines.length * design.tableLine + design.tableCellPaddingY * 2)));
      return { cells, height };
    });
    return { columnWidths, rowLayouts, height: rowLayouts.reduce((sum, row) => sum + row.height, 0) };
  };

  const measureBlock = (context, block, design, contentWidth) => {
    const innerWidth = contentWidth - design.sectionPaddingX * 2;
    let height = design.headingLine + design.sectionTitlePaddingY * 2 + 4;
    const paragraphLayouts = [];
    setFont(context, design.bodySize, 400);
    block.paragraphs.forEach((paragraph) => {
      const lines = wrapText(context, paragraph, innerWidth);
      paragraphLayouts.push(lines);
      height += lines.length * design.bodyLine + 4;
    });
    const tableLayouts = block.tables.map((table, index) => {
      const tableLayout = measureTable(context, table, innerWidth, design, block.tableWidths?.[index]);
      height += tableLayout.height + 6;
      return tableLayout;
    });
    // Dipnot: tablodan SONRA, küçük puntoyla. Hücrede kısa atıf duruyor
    // ("s. 66-67"), belgenin tam adı burada bir kez.
    const noteLayouts = [];
    setFont(context, design.metaSize, 400);
    (block.notes || []).forEach((note) => {
      const lines = wrapText(context, note, innerWidth);
      noteLayouts.push(lines);
      height += lines.length * design.metaLine + 4;
    });
    return { height, paragraphLayouts, tableLayouts, noteLayouts };
  };

  const measureHeader = (context, model, design, contentWidth) => {
    setFont(context, 18, 700);
    setFont(context, design.titleSize, 800);
    const titleLines = wrapText(context, model.title, contentWidth);
    return {
      titleLines,
      height: titleLines.length * design.titleLine + 10
    };
  };

  const buildLayout = (model, design) => {
    const pageHeight = Math.floor(design.renderWidth * (design.a4HeightPt / design.a4WidthPt));
    const contentWidth = design.renderWidth - design.contentX * 2;
    const measureCanvas = document.createElement("canvas");
    const context = measureCanvas.getContext("2d");
    const items = [];
    let y = design.pageMargin;

    const header = measureHeader(context, model, design, contentWidth);
    items.push({ type: "header", y, height: header.height, header });
    y += header.height + design.cardGap;

    model.blocks.forEach((block) => {
      const layout = measureBlock(context, block, design, contentWidth);
      const pageOffset = y % pageHeight;
      const printableBottom = pageHeight - design.pageMargin;
      if (layout.height <= pageHeight - design.pageMargin * 2 && pageOffset + layout.height > printableBottom) {
        y += pageHeight - pageOffset + design.pageMargin;
      }
      items.push({ type: "block", y, height: layout.height, block, layout });
      y += layout.height + design.cardGap;
    });

    return { items, height: Math.ceil(y + design.pageMargin), pageHeight, contentWidth };
  };

  const drawHeader = (context, item, model, design, contentWidth) => {
    const { colors } = design;
    let cursorY = item.y;
    setFont(context, design.titleSize, 800);
    context.fillStyle = colors.navy;
    item.header.titleLines.forEach((line) => {
      context.fillText(line, design.contentX + (contentWidth - context.measureText(line).width) / 2, cursorY);
      cursorY += design.titleLine;
    });
  };

  const drawTable = (context, tableLayout, x, y, width, design) => {
    const { colors } = design;
    let cursorY = y;
    tableLayout.rowLayouts.forEach((row) => {
      let cursorX = x;
      row.cells.forEach((cell, columnIndex) => {
        const columnWidth = tableLayout.columnWidths[columnIndex];
        const cellX = cursorX;
        context.fillStyle = cell.header ? colors.paleBlue : (cell.label ? colors.light : "#ffffff");
        context.fillRect(cellX, cursorY, columnWidth, row.height);
        context.strokeStyle = colors.border;
        context.lineWidth = 1;
        context.strokeRect(cellX, cursorY, columnWidth, row.height);
        context.fillStyle = cell.header ? colors.navy : colors.ink;
        setFont(context, design.tableSize, cell.header || cell.label ? 800 : 400);
        drawLines(context, cell.lines, cellX + design.tableCellPaddingX, cursorY + design.tableCellPaddingY, design.tableLine);
        cursorX += columnWidth;
      });
      cursorY += row.height;
    });
    return cursorY;
  };

  const drawBlock = (context, item, design, contentWidth) => {
    const { colors } = design;
    const x = design.contentX;
    let cursorY = item.y;
    context.fillStyle = colors.blue;
    context.fillRect(x, cursorY, contentWidth, design.headingLine + design.sectionTitlePaddingY * 2);
    setFont(context, design.headingSize, 800);
    context.fillStyle = "#ffffff";
    context.fillText(item.block.heading, x + design.sectionTitlePaddingX, cursorY + design.sectionTitlePaddingY);
    cursorY += design.headingLine + design.sectionTitlePaddingY * 2 + 4;

    const innerX = x + design.sectionPaddingX;
    const innerWidth = contentWidth - design.sectionPaddingX * 2;
    setFont(context, design.bodySize, 400);
    context.fillStyle = colors.ink;
    item.layout.paragraphLayouts.forEach((lines) => {
      cursorY = drawLines(context, lines, innerX, cursorY, design.bodyLine) + 4;
    });
    item.layout.tableLayouts.forEach((tableLayout) => {
      cursorY = drawTable(context, tableLayout, innerX, cursorY, innerWidth, design) + 6;
    });
    setFont(context, design.metaSize, 400);
    context.fillStyle = colors.muted;
    (item.layout.noteLayouts || []).forEach((lines) => {
      cursorY = drawLines(context, lines, innerX, cursorY, design.metaLine) + 4;
    });
  };

  const renderReportToCanvas = (model, design) => {
    const layout = buildLayout(model, design);
    const canvas = document.createElement("canvas");
    canvas.width = Math.ceil(design.renderWidth * design.renderScale);
    canvas.height = Math.ceil(layout.height * design.renderScale);
    const context = canvas.getContext("2d");
    context.scale(design.renderScale, design.renderScale);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, design.renderWidth, layout.height);
    context.textBaseline = "top";
    layout.items.forEach((item) => item.type === "header" ? drawHeader(context, item, model, design, layout.contentWidth) : drawBlock(context, item, design, layout.contentWidth));
    return { canvas, pageHeight: layout.pageHeight };
  };

  const base64ToBytes = (base64) => {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  };

  const canvasToPageImages = (canvas, pageHeight, design) => {
    const sliceHeight = Math.floor(pageHeight * design.renderScale);
    const pages = [];
    for (let y = 0; y < canvas.height; y += sliceHeight) {
      const currentHeight = Math.min(sliceHeight, canvas.height - y);
      const pageCanvas = document.createElement("canvas");
      pageCanvas.width = canvas.width;
      pageCanvas.height = currentHeight;
      const context = pageCanvas.getContext("2d");
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, pageCanvas.width, pageCanvas.height);
      context.drawImage(canvas, 0, y, canvas.width, currentHeight, 0, 0, pageCanvas.width, currentHeight);
      const jpeg = pageCanvas.toDataURL("image/jpeg", 0.93).split(",")[1];
      pages.push({
        bytes: base64ToBytes(jpeg),
        imageWidth: pageCanvas.width,
        imageHeight: pageCanvas.height,
        displayHeight: Math.min(design.a4HeightPt, (pageCanvas.height / pageCanvas.width) * design.a4WidthPt)
      });
    }
    return pages;
  };

  const buildPdf = (pages, design) => {
    const chunks = [];
    const offsets = [];
    let offset = 0;
    const addBytes = (bytes) => { chunks.push(bytes); offset += bytes.length; };
    const addText = (text) => addBytes(encoder.encode(text));
    const startObject = (number) => { offsets[number] = offset; addText(`${number} 0 obj\n`); };
    const endObject = () => addText("endobj\n");
    addText("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
    startObject(1); addText("<< /Type /Catalog /Pages 2 0 R >>\n"); endObject();
    startObject(2); addText(`<< /Type /Pages /Count ${pages.length} /Kids [${pages.map((_, index) => `${3 + index * 3} 0 R`).join(" ")}] >>\n`); endObject();
    pages.forEach((page, index) => {
      const pageObject = 3 + index * 3;
      const contentObject = pageObject + 1;
      const imageObject = pageObject + 2;
      const imageName = `Im${index + 1}`;
      const y = design.a4HeightPt - page.displayHeight;
      const stream = `q\n${design.a4WidthPt.toFixed(2)} 0 0 ${page.displayHeight.toFixed(2)} 0 ${y.toFixed(2)} cm\n/${imageName} Do\nQ`;
      startObject(pageObject);
      addText(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${design.a4WidthPt} ${design.a4HeightPt}] /Resources << /XObject << /${imageName} ${imageObject} 0 R >> >> /Contents ${contentObject} 0 R >>\n`);
      endObject();
      startObject(contentObject);
      addText(`<< /Length ${encoder.encode(stream).length} >>\nstream\n${stream}\nendstream\n`);
      endObject();
      startObject(imageObject);
      addText(`<< /Type /XObject /Subtype /Image /Width ${page.imageWidth} /Height ${page.imageHeight} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.bytes.length} >>\nstream\n`);
      addBytes(page.bytes);
      addText("\nendstream\n");
      endObject();
    });
    const xrefOffset = offset;
    const objectCount = 2 + pages.length * 3;
    addText(`xref\n0 ${objectCount + 1}\n0000000000 65535 f \n`);
    for (let objectNumber = 1; objectNumber <= objectCount; objectNumber += 1) addText(`${String(offsets[objectNumber]).padStart(10, "0")} 00000 n \n`);
    addText(`trailer\n<< /Size ${objectCount + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`);
    return new Blob(chunks, { type: "application/pdf" });
  };

  const triggerDownload = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const downloadReportPdf = async (reportElement, options = {}) => {
    const common = getCommon();
    const model = common.syncOutputHeader(reportElement) || common.getReportModel(reportElement);
    if (!model.validation.valid) throw new Error(model.validation.message);
    const design = common.design;
    const filename = options.filename || "MAHIR_Sinav_Sonuclari_Analiz_Raporu.pdf";
    const rendered = renderReportToCanvas(model, design);
    const pages = canvasToPageImages(rendered.canvas, rendered.pageHeight, design);
    const pdfBlob = buildPdf(pages, design);
    triggerDownload(pdfBlob, filename);
    return { filename, pageCount: pages.length, size: pdfBlob.size };
  };

  window.MAHIRPdfExporter = { downloadReportPdf };
})();
