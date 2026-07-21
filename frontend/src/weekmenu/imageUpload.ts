// Afbeelding-upload client-side: valideren + base64-encoderen. Zelfde limieten
// als de backend (ALLOWED_IMAGE_MEDIA_TYPES / MAX_IMAGE_BYTES in schemas.py).

export const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024

export interface UploadedImage {
  base64: string
  mediaType: string
  /** data-URI voor de preview in het formulier. */
  previewUrl: string
}

export function readImageFile(file: File): Promise<UploadedImage> {
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
    return Promise.reject(new Error('Kies een JPEG-, PNG-, WebP- of GIF-afbeelding.'))
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return Promise.reject(new Error('Afbeelding is te groot (max 5 MB).'))
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Afbeelding lezen mislukt — probeer opnieuw.'))
    reader.onload = () => {
      const dataUrl = reader.result as string
      const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1)
      resolve({ base64, mediaType: file.type, previewUrl: dataUrl })
    }
    reader.readAsDataURL(file)
  })
}
