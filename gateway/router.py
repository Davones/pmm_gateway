import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger()


class Router:
    def __init__(self, routing_table: List, backend_map: Dict[str, str]):
        self.routing_table = routing_table
        self.backend_map = backend_map
        # 启动时预构建: uri -> [(compiled_conditions, target), ...]
        # 避免每个请求都重建分组表和重新编译正则
        self._groups: Dict[str, List] = {}
        for rule in routing_table:
            compiled = [
                (condition.field, re.compile(condition.regex, re.IGNORECASE))
                for condition in (rule.conditions or [])
            ]
            self._groups.setdefault(rule.uri, []).append((compiled, rule.target))

    def route(self, uri: str, request_data: Dict[str, Any]) -> Optional[str]:
        uri = uri.lstrip('/')
        rules = self._groups.get(uri)

        if not rules:
            logger.warning(f"No routing rules found for uri: {uri}")
            return None

        for conditions, target in rules:
            if self._match_conditions(conditions, request_data):
                backend_addr = self.backend_map.get(target)
                logger.debug(f"Routed {uri} to {target} ({backend_addr})")
                return backend_addr

        logger.warning(f"No matching rule found for uri: {uri}, using default")
        return None

    @staticmethod
    def _match_conditions(conditions, request_data: Dict[str, Any]) -> bool:
        if not conditions:
            return True

        for field, pattern in conditions:
            field_value = request_data.get(field)
            if field_value is None:
                logger.debug(f"Field '{field}' not found in request data")
                return False

            if not pattern.match(str(field_value)):
                logger.debug(f"Field '{field}' value '{field_value}' does not match regex '{pattern.pattern}'")
                return False

        return True
