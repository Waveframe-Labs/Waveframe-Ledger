# Ledger 0.9.0 candidate evidence

Draft PR: https://github.com/Waveframe-Labs/Waveframe-Ledger/pull/24

Exact candidate head: `3cc34e7b3cb6efca5102e0e22d559ec0c0fd583f`. Base: `40e0875ee9a973254bb3a4d0c228cad4fdce2bc0`. Compiler: `ae590dee058d3481e384dea850d5b7d980f533ff`.

All four Windows/Linux x Python 3.10/3.14 base acceptance cells passed. Combined
Guard-extra acceptance is **PENDING**, unexecuted, awaiting the separate real Guard
0.19.0 candidate. This is not fully release-ready. No merge/tag/publication/activation.

`handoff.json` records verified archive hashes, package metadata, matrix evidence,
installed paths and Compiler provenance, historical hashes and remaining gates.
The ZIPs contain complete CI reports/logs/JUnit, Ledger wheel/sdist, and the locally
built exact Compiler wheel. They are retained in Git beyond CI artifact expiry.
They are candidate build identities, not selected final authorized release artifacts.

| Environment | Ledger wheel SHA-256 | Ledger sdist SHA-256 | Download |
| --- | --- | --- | --- |
| ubuntu-3.10 | `733defe98588b846a6e90454fa0e07b289ede3af0c9c25ba377f53423c7e4ffb` | `07ed5608ce0b7f8b7c51ad9cf658f867fced43767a5e72ec1affe03d55111327` | [ZIP](artifacts/ubuntu-3.10.zip) |
| ubuntu-3.14 | `ae239faf211bb6bd0885f7873f17a8dfd893a5fb961aac8d6917e4ee4af704be` | `1aa8a67f2846e064e39476b6af449e1401170c975b39d286fb73eadb93d4deb4` | [ZIP](artifacts/ubuntu-3.14.zip) |
| windows-3.10 | `9d16d0befe27378d14aa033067ae4426c370c091a3205457ba35bb30ceb69502` | `d60eb84a735a2aaf2c38dfc867d7f8eb5526781cd97289ee11776ae86c48e33e` | [ZIP](artifacts/windows-3.10.zip) |
| windows-3.14 | `f76242c190275034b33faff4477ef0144dd83e779b832878de7467d483c7076c` | `c6088fed8d130a91befbe62eb741d7f30c1f2b9d3fdd2d208ce3ea834b3d51ac` | [ZIP](artifacts/windows-3.14.zip) |
