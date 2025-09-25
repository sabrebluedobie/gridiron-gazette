import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def _post_process_document(doc_path: str) -> None:
    """
    Post-process the document to fix formatting issues.
    Complete version with all functionality:
    1. Removes empty paragraphs that cause blank pages
    2. Fixes section breaks
    3. Adjusts margins for consistency
    4. Removes excessive spacing
    5. Fixes header/footer alignment
    6. Fixes table formatting
    """
    logger.info("Post-processing document to fix formatting issues...")
    
    try:
        # Try to use the dedicated formatter module first
        from document_formatter import apply_formatting_fixes
        apply_formatting_fixes(doc_path)
        logger.info("✅ Document formatting fixed using dedicated formatter")
        return
    except ImportError:
        logger.info("document_formatter module not found, using comprehensive fallback method")
    except Exception as e:
        logger.warning(f"Error using document_formatter: {e}, using comprehensive fallback method")
    
    # Comprehensive fallback method with ALL functionality
    try:
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.section import WD_SECTION
        from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        
        # Open the document for post-processing
        doc = Document(doc_path)
        
        # Fix margins for all sections (prevents margin slip)
        for section in doc.sections:
            # Use 1.0" top/bottom for header/footer space
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)
            
            # Set header/footer distances to prevent overlap with content
            section.header_distance = Inches(0.5)
            section.footer_distance = Inches(0.5)
            
            # Ensure consistent page size
            section.page_height = Inches(11)
            section.page_width = Inches(8.5)
            
            # Remove unnecessary section breaks that cause blank pages
            # Keep first section as is, make others continuous
            if section != doc.sections[0]:
                section.start_type = WD_SECTION.CONTINUOUS
        
        # Fix header/footer alignment to prevent gradient sliding
        for section in doc.sections:
            # Fix header alignment
            header = section.header
            for paragraph in header.paragraphs:
                paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                paragraph_format = paragraph.paragraph_format
                paragraph_format.left_indent = Inches(0)
                paragraph_format.right_indent = Inches(0)
                
            # Fix footer alignment  
            footer = section.footer
            for paragraph in footer.paragraphs:
                paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                paragraph_format = paragraph.paragraph_format
                paragraph_format.left_indent = Inches(0)
                paragraph_format.right_indent = Inches(0)
        
        # Remove empty paragraphs that cause blank pages
        paragraphs_to_delete = []
        consecutive_empty = 0
        
        for i, paragraph in enumerate(doc.paragraphs):
            # Check if paragraph is effectively empty
            text = paragraph.text.strip()
            
            if not text:
                # Check if it has no runs with images either
                has_content = False
                for run in paragraph.runs:
                    if run.text.strip():
                        has_content = True
                        break
                    # Check for embedded objects (images)
                    if hasattr(run, '_element') and run._element.xpath('.//w:drawing'):
                        has_content = True
                        break
                
                if not has_content:
                    consecutive_empty += 1
                    # Keep single empty paragraphs for spacing, remove multiple consecutive ones
                    if consecutive_empty > 1:
                        paragraphs_to_delete.append(paragraph)
            else:
                consecutive_empty = 0
        
        # Delete excessive empty paragraphs
        for paragraph in paragraphs_to_delete:
            try:
                p = paragraph._element
                p.getparent().remove(p)
                logger.debug("Removed empty paragraph")
            except:
                pass  # Paragraph might already be removed
        
        # Fix spacing between paragraphs
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():  # Only for non-empty paragraphs
                paragraph_format = paragraph.paragraph_format
                
                # Consistent spacing
                paragraph_format.space_after = Pt(6)  # Reduced from default
                paragraph_format.space_before = Pt(6)  # Reduced from default
                
                # Ensure single line spacing with slight increase for readability
                paragraph_format.line_spacing = 1.15
                
                # Remove excessive indentation that might cause margin issues
                if paragraph_format.left_indent and paragraph_format.left_indent > Inches(0.5):
                    paragraph_format.left_indent = Inches(0)
                if paragraph_format.right_indent and paragraph_format.right_indent > Inches(0.5):
                    paragraph_format.right_indent = Inches(0)
        
        # Remove unnecessary page breaks
        for paragraph in doc.paragraphs:
            if hasattr(paragraph, '_element'):
                # Check for page breaks
                page_breaks = paragraph._element.xpath('.//w:br[@w:type="page"]')
                if page_breaks:
                    # Check if this paragraph has actual content
                    if not paragraph.text.strip():
                        # Remove unnecessary page break
                        for br in page_breaks:
                            br.getparent().remove(br)
                            logger.debug("Removed unnecessary page break")
        
        # Handle tables to prevent margin issues
        for table in doc.tables:
            table.autofit = True
            # Set table alignment to center
            table.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            
            # Fix table properties to prevent overflow
            tbl = table._element
            tblPr = tbl.xpath('.//w:tblPr')[0] if tbl.xpath('.//w:tblPr') else tbl.add_tblPr()
            
            # Set table width to auto
            tblW = OxmlElement('w:tblW')
            tblW.set(qn('w:type'), 'auto')
            tblW.set(qn('w:w'), '0')
            
            # Remove any existing width settings
            for existing_tblW in tblPr.xpath('.//w:tblW'):
                tblPr.remove(existing_tblW)
            
            tblPr.append(tblW)
            
            # Ensure table doesn't exceed margins
            for row in table.rows:
                for cell in row.cells:
                    # Set cell margins
                    tc = cell._element
                    tcPr = tc.get_or_add_tcPr()
                    
                    # Remove any existing margins
                    for tcMar in tcPr.xpath('.//w:tcMar'):
                        tcPr.remove(tcMar)
                    
                    # Add consistent small margins
                    tcMar = OxmlElement('w:tcMar')
                    for margin_type in ['top', 'left', 'bottom', 'right']:
                        margin = OxmlElement(f'w:{margin_type}')
                        margin.set(qn('w:w'), '50')  # Small margin
                        margin.set(qn('w:type'), 'dxa')
                        tcMar.append(margin)
                    tcPr.append(tcMar)
                    
                    # Fix cell paragraph spacing
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.space_after = Pt(3)
                        paragraph.paragraph_format.space_before = Pt(3)
                        paragraph.paragraph_format.line_spacing = 1.0
        
        # Save the fixed document
        doc.save(doc_path)
        logger.info(f"✅ Post-processing complete: fixed margins, removed blank pages, aligned headers/footers")
        
    except Exception as e:
        logger.error(f"Error during post-processing: {e}")
        # Don't fail the entire process if post-processing fails
        logger.info("Document generated but post-processing failed - output may have formatting issues")