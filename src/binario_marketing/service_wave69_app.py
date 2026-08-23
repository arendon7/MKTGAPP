from __future__ import annotations

import json
import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave68_app as base
from .physical_uat_store import machine_snapshot
from .release_contract import evaluate_source_release_contract
from .version import RELEASE_READY, RELEASE_TAG, __version__


class AppRuntime(base.AppRuntime):
    """Wave 69 verifies physical-UAT prerequisites without satisfying the physical gate."""

    def _wave69_resources_root(self) -> Path:
        candidates=[self.repo_root.parent,self.repo_root]
        for candidate in candidates:
            if (candidate/"runtime").is_dir() or (candidate/"BUILD_PROVENANCE.json").is_file(): return candidate
        return self.repo_root

    def _physical_uat_candidate_manifest(self)->dict:
        path=self._wave69_resources_root()/"PHYSICAL_UAT_CANDIDATE.json"
        if not path.is_file(): return {}
        try: row=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError,TypeError): return {}
        return row if isinstance(row,dict) else {}

    @staticmethod
    def _trusted_physical_uat_candidate(candidate:dict,build:dict)->bool:
        origin=candidate.get("build_origin") if isinstance(candidate.get("build_origin"),dict) else {}; physical=candidate.get("physical_uat") if isinstance(candidate.get("physical_uat"),dict) else {}
        return bool(candidate.get("schema")=="binario.marketing.physical-uat-candidate.v1" and candidate.get("role")=="PHYSICAL_UAT_CANDIDATE_ONLY" and candidate.get("git_sha")==build.get("git_sha") and candidate.get("architecture")==build.get("architecture")=="arm64" and candidate.get("product_version")==build.get("product_version")==__version__ and candidate.get("runtime_wave")==76 and candidate.get("certification_guard_wave")==84 and isinstance(candidate.get("candidate_source_sha256"),str) and len(candidate.get("candidate_source_sha256"))==64 and origin.get("event")=="push" and origin.get("ref")=="refs/heads/main" and origin.get("trusted_for_physical_uat") is True and physical.get("eligible_build_origin") is True and physical.get("automatic_pass") is False)

    @staticmethod
    def _candidate_release_contract(candidate:dict)->dict:
        boundary=candidate.get("release_boundary") if isinstance(candidate.get("release_boundary"),dict) else {}
        try:
            contract=evaluate_source_release_contract(version=str(candidate.get("product_version") or ""),release_ready=boundary.get("release_ready") is True,release_tag=boundary.get("release_tag"))
        except ValueError:
            return {}
        if boundary.get("mode") not in {None,contract.get("mode")}: return {}
        if boundary.get("production_ready") is True or boundary.get("release_authority") is True or boundary.get("operational_authorization") is True: return {}
        return contract

    def physical_uat_preflight(self,company_id:str)->dict:
        company=self.companies.get(company_id); machine=machine_snapshot(); build=self._build_provenance(); candidate=self._physical_uat_candidate_manifest(); overview=self.physical_uat_overview(company.id); resources=self._wave69_resources_root(); runtime=resources/"runtime"
        paths={"python":runtime/"python/bin/python3","ffmpeg":runtime/"media/bin/ffmpeg","ffprobe":runtime/"media/bin/ffprobe","whisper_cli":runtime/"transcription/bin/whisper-cli","whisper_manifest":runtime/"transcription/RUNTIME.json"}
        model_dir=runtime/"transcription/models"; model_present=model_dir.is_dir() and any(path.is_file() for path in model_dir.glob("ggml-*.bin")); executable_runtime=all(path.is_file() and os.access(path,os.X_OK) for key,path in paths.items() if key!="whisper_manifest"); manifests_present=paths["whisper_manifest"].is_file(); embedded_runtime_ready=executable_runtime and manifests_present and model_present
        provenance_present=build.get("source")=="BUILD_PROVENANCE.json"; trusted_candidate=self._trusted_physical_uat_candidate(candidate,build); architecture_matches=str(build.get("architecture") or "").lower()=="arm64"; version_matches=str(build.get("product_version") or "")==__version__
        try: source_release_contract=evaluate_source_release_contract(version=__version__,release_ready=RELEASE_READY,release_tag=RELEASE_TAG)
        except ValueError as exc: source_release_contract={"mode":"INVALID","error":str(exc),"release_ready":RELEASE_READY,"release_tag":RELEASE_TAG,"production_ready":False,"release_authority":False}
        candidate_release_contract=self._candidate_release_contract(candidate)
        release_contract_matches=bool(candidate_release_contract and candidate_release_contract.get("mode")==source_release_contract.get("mode") and candidate_release_contract.get("release_ready")==source_release_contract.get("release_ready") and candidate_release_contract.get("release_tag")==source_release_contract.get("release_tag"))
        non_production_distribution=str(build.get("release_channel") or "development")=="development" and str(build.get("signing_mode") or "ad_hoc")=="ad_hoc" and build.get("notarized") is False
        fail_closed_release=bool(source_release_contract.get("mode")!="INVALID" and release_contract_matches and non_production_distribution and source_release_contract.get("production_ready") is False and source_release_contract.get("release_authority") is False)
        data_root_ready=self.data_root.is_dir() and os.access(self.data_root,os.R_OK|os.W_OK|os.X_OK)
        def check(check_id,label,passed,detail,required=True): return {"id":check_id,"label":label,"status":"PASS" if passed else "BLOCKED","passed":bool(passed),"required":required,"detail":detail}
        origin=candidate.get("build_origin") if isinstance(candidate.get("build_origin"),dict) else {}
        checks=[
            check("physical-machine","Mac físico arm64 elegible",bool(machine.get("physical_gate_eligible")),f"{machine.get('system')} · {machine.get('machine')} · CI={machine.get('is_ci')}"),
            check("certified-build-provenance","Provenance del .app disponible",provenance_present,"BUILD_PROVENANCE.json" if provenance_present else "Checkout fuente sin provenance de bundle"),
            check("trusted-build-candidate","Candidato físico exacto de origen GitHub confiable",trusted_candidate,"push · refs/heads/main · PHYSICAL_UAT_CANDIDATE_ONLY" if trusted_candidate else f"role={candidate.get('role') or 'missing'} · event={origin.get('event') or 'unknown'} · ref={origin.get('ref') or 'unknown'}"),
            check("arm64-build","Build arm64",architecture_matches,f"architecture={build.get('architecture') or 'unknown'}"),
            check("version-contract","Versión canónica",version_matches,f"build={build.get('product_version') or 'unknown'} · expected={__version__}"),
            check("embedded-runtime","Runtime embebido completo",embedded_runtime_ready,"CPython + FFmpeg/FFprobe + whisper-cli + modelo + manifest" if embedded_runtime_ready else "Falta uno o más componentes embebidos del bundle"),
            check("local-data-root","Datos locales accesibles",data_root_ready,"Directorio local legible/escribible" if data_root_ready else "Directorio local no accesible"),
            check("release-fail-closed","Sin autoridad operativa de release",fail_closed_release,f"source={source_release_contract.get('mode')} · signing={build.get('signing_mode') or 'unknown'} · notarized={build.get('notarized')} · production_ready=False" if fail_closed_release else f"source={source_release_contract} · candidate={candidate_release_contract} · build_channel={build.get('release_channel')}"),
            check("loopback-default","Servidor local loopback",True,"127.0.0.1 por defecto; no se requiere bind público"),
        ]
        blockers=[row["id"] for row in checks if row["required"] and not row["passed"]]; ready=not blockers; readiness=overview.get("readiness") or {}; manual_scenarios=list(readiness.get("manual_scenarios") or []); required_scenarios=[row for row in manual_scenarios if row.get("id")!="optional-ai"]
        if overview.get("active_session") and ready: next_action={"code":"CONTINUE_SESSION","label":"Continuar sesión UAT activa"}
        elif ready: next_action={"code":"START_PHYSICAL_UAT","label":"Iniciar UAT física guiada"}
        else: next_action={"code":"RESOLVE_PREFLIGHT","label":"Resolver bloqueos de preflight"}
        return {"schema":"binario.marketing.physical-uat-preflight.v1","company":{"id":company.id,"name":company.name},"machine":machine,"build":build,"candidate":{"schema":candidate.get("schema"),"role":candidate.get("role"),"git_sha":candidate.get("git_sha"),"candidate_source_sha256":candidate.get("candidate_source_sha256"),"build_origin":origin,"trusted_for_physical_uat":trusted_candidate,"source_release_contract":candidate_release_contract},"checks":checks,"blockers":blockers,"ready_to_begin_physical_uat":ready,"physical_uat_complete":bool(overview.get("physical_uat_complete")),"active_session_id":(overview.get("active_session") or {}).get("id"),"scenario_contract":{"required":len(required_scenarios),"optional":max(0,len(manual_scenarios)-len(required_scenarios)),"automatic_pass":False,"manual_evidence_required":True},"next_action":next_action,"release_boundary":{**source_release_contract,"physical_preflight_is_release_authority":False},"safety":{"provider_read_performed":False,"provider_mutation_performed":False,"marketing_mutation_performed":False,"physical_uat_result_recorded":False,"background_polling":False,"cloud_required":False}}

    def _require_physical_uat_preflight(self,company_id:str)->None:
        preflight=self.physical_uat_preflight(company_id)
        if not preflight.get("ready_to_begin_physical_uat"):
            blockers=", ".join(preflight.get("blockers") or ["unknown"]); raise ValueError(f"physical UAT preflight blocked: {blockers}")

    def start_physical_uat(self,company_id:str,payload:dict)->dict:
        self._require_physical_uat_preflight(company_id); return super().start_physical_uat(company_id,payload)

    def update_physical_uat_scenario(self,company_id:str,session_id:str,scenario_id:str,payload:dict)->dict:
        self._require_physical_uat_preflight(company_id); return super().update_physical_uat_scenario(company_id,session_id,scenario_id,payload)

    def finish_physical_uat(self,company_id:str,session_id:str)->dict:
        self._require_physical_uat_preflight(company_id); return super().finish_physical_uat(company_id,session_id)


MarketingHTTPServer=base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 69 adds only a local GET preflight and browser status layer."""
    def _static(self,path:str)->None:
        if path=="/guided-physical-uat.js":
            target=self.server.runtime.repo_root/"web/guided-physical-uat.js"
            if not target.is_file(): self._error(HTTPStatus.NOT_FOUND,"not found"); return
            bootstrap="""
;(function loadWave69PhysicalUATPreflight(){
  if(document.querySelector('script[data-physical-uat-preflight-wave69]'))return;
  const preflight=document.createElement('script');
  preflight.src='/physical-uat-preflight.js';
  preflight.defer=true;
  preflight.dataset.physicalUatPreflightWave69='1';
  document.head.append(preflight);
})();
"""
            body=(target.read_text(encoding="utf-8")+bootstrap).encode("utf-8"); self._headers(HTTPStatus.OK,"application/javascript; charset=utf-8",len(body)); self.wfile.write(body); return
        super()._static(path)
    def do_GET(self)->None:
        path=urlparse(self.path).path
        if path=="/physical-uat-preflight.js": self._static(path); return
        parts=self._segments()
        try:
            if len(parts)==5 and parts[:2]==["api","companies"] and parts[3:]==["physical-uat","preflight"]: self._json(self.server.runtime.physical_uat_preflight(parts[2])); return
        except Exception as exc: self._wave67_error(exc); return
        super().do_GET()


def create_server(runtime:AppRuntime,host:str="127.0.0.1",port:int=8765)->MarketingHTTPServer: return MarketingHTTPServer((host,port),MarketingHandler,runtime)


def serve(host:str="127.0.0.1",port:int=8765,*,allow_network:bool=False,open_browser:bool=False)->None:
    if host not in {"127.0.0.1","localhost","::1"} and not allow_network: raise ValueError("refusing non-loopback bind without --allow-network")
    runtime=AppRuntime.create(); server=create_server(runtime,host,port); actual_host,actual_port=server.server_address[:2]; url=f"http://{actual_host}:{actual_port}/"; print(f"BINARIO Marketing App: {url}"); print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser; webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__=["AppRuntime","MarketingHandler","MarketingHTTPServer","create_server","serve"]
