"""CLI: python -m datagen.cli [flags]

Every dataclass field of GenerationConfig is exposed as a flag with the
same name (dashes for underscores). --config PATH loads a truth.json's
`config` block; further flags override it.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import fields

from .anomalies import inject_anomalies
from .config import GenerationConfig
from .emitters import emit
from .network import sample_edges, sample_gstins
from .rings import plant_rings
from .transactions import derive_returns, sample_transactions


def _add_config_flags(parser: argparse.ArgumentParser) -> None:
    defaults = GenerationConfig()
    for f in fields(GenerationConfig):
        flag = "--" + f.name.replace("_", "-")
        default = getattr(defaults, f.name)
        typ = type(default) if default is not None else str
        if typ is bool:
            parser.add_argument(flag, action=argparse.BooleanOptionalAction, default=default)
        else:
            parser.add_argument(flag, type=typ, default=default, help=f"default: {default}")


def build_config(args: argparse.Namespace) -> GenerationConfig:
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            data = json.load(f).get("config", {})
        cfg = GenerationConfig.from_dict(data)
        # apply overrides from CLI (only if user set them; argparse can't tell,
        # so we just take the CLI value which defaults to config's value)
        for f in fields(GenerationConfig):
            v = getattr(args, f.name)
            if v is not None:
                setattr(cfg, f.name, v)
        return cfg
    return GenerationConfig(**{f.name: getattr(args, f.name) for f in fields(GenerationConfig)})


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
    log = logging.getLogger("datagen.cli")
    p = argparse.ArgumentParser(
        prog="datagen.cli",
        description="Generate a synthetic Indian GST dataset with ground truth.",
    )
    p.add_argument("--config", type=str, default=None,
                    help="Path to a truth.json — its 'config' block is loaded as defaults.")
    _add_config_flags(p)
    args = p.parse_args(argv)

    cfg = build_config(args)
    cfg.validate()
    log.info("Generating with seed=%d, n_gstins=%d, months=%d, out=%s",
             cfg.seed, cfg.n_gstins, cfg.months, cfg.out_dir)

    t0 = time.perf_counter()
    gstins = sample_gstins(cfg)
    t_gstins = time.perf_counter()
    log.info("sampled %d GSTINs in %.2fs", len(gstins), t_gstins - t0)

    edges = sample_edges(cfg, gstins)
    t_edges = time.perf_counter()
    log.info("sampled %d supplier→buyer edges in %.2fs", len(edges), t_edges - t_gstins)

    bundles = sample_transactions(cfg, gstins, edges)
    t_bundles = time.perf_counter()
    log.info("sampled %d invoice bundles in %.2fs", len(bundles), t_bundles - t_edges)

    ring_bundles, ring_g1, ring_g3, ring_tp, planted_rings = plant_rings(cfg, gstins)
    ring_invoice_ids = {b.invoice.invoice_id for b in ring_bundles}
    bundles = bundles + ring_bundles

    gstr1s, gstr3bs, gstr2bs, taxpays = derive_returns(cfg, gstins, bundles)
    # merge in ring returns/payments
    gstr1s.extend(ring_g1); gstr3bs.extend(ring_g3); taxpays.extend(ring_tp)
    t_returns = time.perf_counter()
    log.info("derived returns / payments in %.2fs", t_returns - t_bundles)

    bundles, gstr1s, gstr3bs, taxpays, planted_anoms = inject_anomalies(
        cfg, bundles, gstr1s, gstr3bs, taxpays,
        ring_invoice_ids=ring_invoice_ids,
        gstin_meta_records=gstins,
    )
    t_anoms = time.perf_counter()
    log.info("injected %d anomalies in %.2fs", len(planted_anoms), t_anoms - t_returns)

    counts = emit(cfg, gstins, bundles, gstr1s, gstr3bs, gstr2bs, taxpays,
                    planted_anoms, planted_rings)
    t_emit = time.perf_counter()
    log.info("emitted CSVs + truth.json in %.2fs", t_emit - t_anoms)

    log.info("done in %.2fs. Files under %s", t_emit - t0, os.path.abspath(cfg.out_dir))
    for k, v in counts.items():
        log.info("  %-18s %d", k, v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
