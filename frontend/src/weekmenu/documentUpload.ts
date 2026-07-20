// Document-upload client-side (Word/PDF): valideren + base64-encoderen. Zelfde
// limieten als de backend (ALLOWED_DOCUMENT_MEDIA_TYPES / MAX_DOCUMENT_BYTES in schemas.py).

export const ALLOWED_DOCUMENT_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]
export const MAX_DOCUMENT_BYTES = 15 * 1024 * 1024

export interface UploadedDocument {
  base64: string
  mediaType: string
}

export function readDocumentFile(file: File): Promise<UploadedDocument> {
  if (!ALLOWED_DOCUMENT_TYPES.includes(file.type)) {
    return Promise.reject(new Error('Kies een Word- (.docx) of PDF-bestand.'))
  }
  if (file.size > MAX_DOCUMENT_BYTES) {
    return Promise.reject(new Error('Bestand is te groot (max 15 MB).'))
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Bestand lezen mislukt — probeer opnieuw.'))
    reader.onload = () => {
      const dataUrl = reader.result as string
      const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1)
      resolve({ base64, mediaType: file.type })
    }
    reader.readAsDataURL(file)
  })
}
