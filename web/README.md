# PayCheck site

Static PayCheck site, live at https://paycheck-guard.vercel.app. The user-facing name is the `PRODUCT_NAME` constant in `src/lib/product.ts`. The npm package name is `paycheck-site`.

```bash
cd web
npm install
npm run dev
npm run build
```

Dev and preview bind to `0.0.0.0` and `PORT` (default 5173). `npm run build` typechecks, then writes `dist/`.

Data shapes and the `runs/` layout are in [DATA.md](./DATA.md).
