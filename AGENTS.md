# Repository Rules - ruangbaca-similarity

## Alur Deployment
- **Production (`main`)**: Update dilakukan dengan push ke repository GitHub. GitHub Actions secara otomatis men-sync commit baru ke Hugging Face Space Production (`ghiyatsa/ruangbaca-similarity`). Jangan melakukan push manual ke space prod.
- **Development (`dev`)**: Update di-push langsung ke Hugging Face Space Development (`ghiyatsa/ruangbaca-similarity-dev`) menggunakan remote `hf-dev`.
