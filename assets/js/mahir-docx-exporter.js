(() => {
  const encoder = new TextEncoder();
  const WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
  const CONTENT_WIDTH_DXA = 10206;

  const crcTable = (() => {
    const table = new Uint32Array(256);
    for (let index = 0; index < 256; index += 1) {
      let value = index;
      for (let bit = 0; bit < 8; bit += 1) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
      table[index] = value >>> 0;
    }
    return table;
  })();

  const common = () => {
    if (!window.MAHIRReportExport) throw new Error("Ortak rapor çıktı modeli yüklenemedi.");
    return window.MAHIRReportExport;
  };

  const crc32 = (bytes) => {
    let crc = 0xffffffff;
    for (let index = 0; index < bytes.length; index += 1) crc = crcTable[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  };

  const escapeXml = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");

  const paragraph = (text, style = "Normal", options = {}) => {
    const bold = options.bold ? "<w:b/>" : "";
    const color = options.color ? `<w:color w:val="${options.color}"/>` : "";
    const size = options.size ? `<w:sz w:val="${options.size}"/><w:szCs w:val="${options.size}"/>` : "";
    const align = options.align ? `<w:jc w:val="${options.align}"/>` : "";
    const keepNext = options.keepNext ? "<w:keepNext/>" : "";
    const spacing = `<w:spacing w:after="${options.after ?? 80}" w:line="${options.line ?? 252}" w:lineRule="auto"/>`;
    return `<w:p><w:pPr><w:pStyle w:val="${style}"/>${keepNext}${align}${spacing}</w:pPr><w:r><w:rPr>${bold}${color}${size}</w:rPr><w:t xml:space="preserve">${escapeXml(text)}</w:t></w:r></w:p>`;
  };

  const cell = (content, options = {}) => {
    const width = options.width ? `<w:tcW w:w="${options.width}" w:type="dxa"/>` : "";
    const shade = options.shade ? `<w:shd w:fill="${options.shade}"/>` : "";
    const gridSpan = options.gridSpan ? `<w:gridSpan w:val="${options.gridSpan}"/>` : "";
    const borders = options.noBorders ? "" : "<w:tcBorders><w:top w:val=\"single\" w:sz=\"4\" w:color=\"9EBCD3\"/><w:left w:val=\"single\" w:sz=\"4\" w:color=\"9EBCD3\"/><w:bottom w:val=\"single\" w:sz=\"4\" w:color=\"9EBCD3\"/><w:right w:val=\"single\" w:sz=\"4\" w:color=\"9EBCD3\"/></w:tcBorders>";
    return `<w:tc><w:tcPr>${width}${gridSpan}${shade}${borders}<w:tcMar><w:top w:w="90" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar></w:tcPr>${content}</w:tc>`;
  };

  const columnWidthsDxa = (weights, columnCount) => {
    const normalized = Array.isArray(weights) && weights.length === columnCount
      ? weights.map((value) => Math.max(Number(value) || 0, 0))
      : Array.from({ length: columnCount }, () => 1);
    const total = normalized.reduce((sum, value) => sum + value, 0) || columnCount;
    let allocated = 0;
    return normalized.map((value, index) => {
      const width = index === columnCount - 1
        ? CONTENT_WIDTH_DXA - allocated
        : Math.floor(CONTENT_WIDTH_DXA * value / total);
      allocated += width;
      return width;
    });
  };

  const tableXml = (rows, options = {}) => {
    if (!rows?.length) return "";
    const columnCount = Math.max(...rows.map((row) => row.length), 1);
    const widths = columnWidthsDxa(options.widths, columnCount);
    const tableRows = rows.map((row, rowIndex) => {
      const rowProps = `<w:trPr><w:cantSplit/>${rowIndex === 0 ? "<w:tblHeader/>" : ""}</w:trPr>`;
      const cells = Array.from({ length: columnCount }, (_, index) => {
        const header = rowIndex === 0;
        const labelColumn = !header && index === 0 && columnCount === 2;
        return cell(paragraph(row[index] || "", "TableText", {
          bold: header || labelColumn,
          color: header ? "17365D" : "1F1F1F",
          after: 0,
          line: 224
        }), { width: widths[index], shade: header ? "D9EAF7" : (labelColumn ? "F8FBFD" : "") });
      }).join("");
      return `<w:tr>${rowProps}${cells}</w:tr>`;
    }).join("");
    return `<w:tbl><w:tblPr><w:tblW w:w="${CONTENT_WIDTH_DXA}" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblInd w:w="0" w:type="dxa"/><w:tblBorders><w:top w:val="single" w:sz="4" w:color="9EBCD3"/><w:left w:val="single" w:sz="4" w:color="9EBCD3"/><w:bottom w:val="single" w:sz="4" w:color="9EBCD3"/><w:right w:val="single" w:sz="4" w:color="9EBCD3"/><w:insideH w:val="single" w:sz="4" w:color="9EBCD3"/><w:insideV w:val="single" w:sz="4" w:color="9EBCD3"/></w:tblBorders></w:tblPr><w:tblGrid>${widths.map((width) => `<w:gridCol w:w="${width}"/>`).join("")}</w:tblGrid>${tableRows}</w:tbl>${options.after === false ? "" : paragraph("", "Normal", { after: 70, line: 120 })}`;
  };

  const sectionBand = (heading) => `<w:tbl><w:tblPr><w:tblW w:w="${CONTENT_WIDTH_DXA}" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblInd w:w="0" w:type="dxa"/><w:tblBorders><w:top w:val="single" w:sz="4" w:color="2F75B5"/><w:left w:val="single" w:sz="4" w:color="2F75B5"/><w:bottom w:val="single" w:sz="4" w:color="2F75B5"/><w:right w:val="single" w:sz="4" w:color="2F75B5"/></w:tblBorders></w:tblPr><w:tblGrid><w:gridCol w:w="${CONTENT_WIDTH_DXA}"/></w:tblGrid><w:tr><w:trPr><w:cantSplit/></w:trPr><w:tc><w:tcPr><w:tcW w:w="${CONTENT_WIDTH_DXA}" w:type="dxa"/><w:shd w:fill="2F75B5"/><w:tcMar><w:top w:w="90" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar></w:tcPr>${paragraph(heading, "SectionTitle", { color: "FFFFFF", bold: true, after: 0, line: 230 })}</w:tc></w:tr></w:tbl>`;

  const sectionXml = (block) => {
    const columnCount = Math.max(...(block.tables || []).flatMap((table) => (table || []).map((row) => row.length)), 1);
    return [
    sectionBand(block.heading),
    ...block.paragraphs.map((text) => paragraph(text, "Normal", { after: 70, line: 252 })),
    ...block.tables.map((table, index) => tableXml(table, { after: true, widths: block.tableWidths?.[index] })),
    // Dipnot tablodan SONRA ve küçük puntoyla: hücrede kısa atıf ("s. 66-67"),
    // belgenin tam adı burada bir kez (bkz. mahir-report-export-common.js
    // sourceNotes). `paragraphs` bu işi göremez - o alan tablonun önünde.
    ...(block.notes || []).map((text) => paragraph(text, "Normal", {
      size: 17, color: "59697A", after: 70, line: 240
    }))
    ].join("");
  };

  const documentXml = (reportElement) => {
    const model = common().syncOutputHeader(reportElement) || common().getReportModel(reportElement);
    if (!model.validation.valid) throw new Error(model.validation.message);
    const body = [
      paragraph(model.title, "ReportTitle", { color: "17365D", size: 28, bold: true, align: "center", keepNext: true, after: 180, line: 320 }),
      ...model.blocks.map(sectionXml)
    ].join("");
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="${WORD_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>${body}<w:sectPr><w:footerReference w:type="default" r:id="rId1"/><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="900" w:right="850" w:bottom="850" w:left="850" w:header="480" w:footer="480" w:gutter="0"/></w:sectPr></w:body></w:document>`;
  };

  const stylesXml = () => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="${WORD_NS}"><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="18"/><w:szCs w:val="18"/><w:color w:val="1F1F1F"/></w:rPr><w:pPr><w:spacing w:line="252" w:lineRule="auto" w:after="80"/></w:pPr></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="44"/><w:szCs w:val="44"/><w:color w:val="17365D"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="20"/><w:szCs w:val="20"/><w:color w:val="365F91"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="ReportTitle"><w:name w:val="Report Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="28"/><w:szCs w:val="28"/><w:color w:val="17365D"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="SectionTitle"><w:name w:val="Section Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:color w:val="FFFFFF"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="17"/><w:szCs w:val="17"/></w:rPr><w:pPr><w:spacing w:after="0" w:line="224" w:lineRule="auto"/></w:pPr></w:style></w:styles>`;

  const footerXml = () => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="${WORD_NS}">${paragraph("MAHİR — Maarif Anlayışıyla Hizmet İşleme ve Raporlama Ajanı", "Normal", { color: "666666", size: 18, align: "center", after: 0 })}</w:ftr>`;
  const documentRelsXml = () => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>`;
  const contentTypesXml = () => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>`;
  const relsXml = () => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml" Target="customXml/mahir-report.xml"/></Relationships>`;

  const bytesToBase64 = (bytes) => {
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
  };

  const portableReportXml = () => {
    const payload = common().getPortableReportPayload();
    const encoded = bytesToBase64(encoder.encode(JSON.stringify(payload)));
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><mahirReport xmlns="urn:mahir:analysis-report:v1"><payload encoding="base64">${encoded}</payload></mahirReport>`;
  };

  const dosDateTime = () => {
    const date = new Date();
    return { time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2), dosDate: ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate() };
  };
  const u16 = (value) => { const bytes = new Uint8Array(2); new DataView(bytes.buffer).setUint16(0, value, true); return bytes; };
  const u32 = (value) => { const bytes = new Uint8Array(4); new DataView(bytes.buffer).setUint32(0, value >>> 0, true); return bytes; };
  const concat = (parts) => { const length = parts.reduce((sum, part) => sum + part.length, 0); const output = new Uint8Array(length); let offset = 0; parts.forEach((part) => { output.set(part, offset); offset += part.length; }); return output; };

  const buildZip = (files) => {
    const { time, dosDate } = dosDateTime();
    const localParts = [];
    const centralParts = [];
    let offset = 0;
    files.forEach((file) => {
      const nameBytes = encoder.encode(file.name);
      const dataBytes = encoder.encode(file.content);
      const crc = crc32(dataBytes);
      const localHeader = concat([u32(0x04034b50), u16(20), u16(0), u16(0), u16(time), u16(dosDate), u32(crc), u32(dataBytes.length), u32(dataBytes.length), u16(nameBytes.length), u16(0), nameBytes]);
      localParts.push(localHeader, dataBytes);
      centralParts.push(concat([u32(0x02014b50), u16(20), u16(20), u16(0), u16(0), u16(time), u16(dosDate), u32(crc), u32(dataBytes.length), u32(dataBytes.length), u16(nameBytes.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset), nameBytes]));
      offset += localHeader.length + dataBytes.length;
    });
    const localData = concat(localParts);
    const centralDirectory = concat(centralParts);
    const endRecord = concat([u32(0x06054b50), u16(0), u16(0), u16(files.length), u16(files.length), u32(centralDirectory.length), u32(localData.length), u16(0)]);
    return new Blob([localData, centralDirectory, endRecord], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
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

  const downloadReportDocx = async (reportElement, options = {}) => {
    if (!reportElement) throw new Error("Word üretimi için rapor alanı bulunamadı.");
    const filename = options.filename || "MAHIR_Sinav_Sonuclari_Analiz_Raporu.docx";
    const blob = buildZip([
      { name: "[Content_Types].xml", content: contentTypesXml() },
      { name: "_rels/.rels", content: relsXml() },
      { name: "word/document.xml", content: documentXml(reportElement) },
      { name: "word/_rels/document.xml.rels", content: documentRelsXml() },
      { name: "word/footer1.xml", content: footerXml() },
      { name: "word/styles.xml", content: stylesXml() },
      { name: "customXml/mahir-report.xml", content: portableReportXml() }
    ]);
    triggerDownload(blob, filename);
    return { filename, size: blob.size };
  };

  window.MAHIRDocxExporter = { downloadReportDocx };
})();

