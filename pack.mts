// Packs build/gmf with the vendored toolkit's native packer (patched for widge_pointer by scripts/setup.sh).
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { packGmfDirectory } from './vendor/band10-toolkit/builder/native.ts'

const root = path.dirname(fileURLToPath(import.meta.url))
const output = path.join(root, 'dist', 'planisphere-watch.bin')
await packGmfDirectory(path.join(root, 'build', 'gmf'), output)
console.log(`packed ${output}`)
