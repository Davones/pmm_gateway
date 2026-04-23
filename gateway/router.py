import re
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger()


class Router:
    def __init__(self, routing_table: List, backend_map: Dict[str, str]):
        self.routing_table = routing_table
        self.backend_map = backend_map

    def _group_by_uri(self) -> Dict[str, List]:
        groups = {}
        for rule in self.routing_table:
            if rule.uri not in groups:
                groups[rule.uri] = []
            groups[rule.uri].append(rule)
        return groups

    def route(self, uri: str, request_data: Dict[str, Any]) -> Optional[str]:
        uri = uri.lstrip('/')
        groups = self._group_by_uri()

        if uri not in groups:
            logger.warning(f"No routing rules found for uri: {uri}")
            return None

        rules = groups[uri]
        for rule in rules:
            if self._match_rule(rule, request_data):
                target = rule.target
                backend_addr = self.backend_map.get(target)
                logger.info(f"Routed {uri} to {target} ({backend_addr})")
                return backend_addr

        logger.warning(f"No matching rule found for uri: {uri}, using default")
        return None

    def _match_rule(self, rule, request_data: Dict[str, Any]) -> bool:
        if not rule.conditions:
            return True

        for condition in rule.conditions:
            field_value = request_data.get(condition.field)
            if field_value is None:
                logger.debug(f"Field '{condition.field}' not found in request data")
                return False

            field_str = str(field_value)
            if not re.match(condition.regex, field_str, re.IGNORECASE):
                logger.debug(f"Field '{condition.field}' value '{field_str}' does not match regex '{condition.regex}'")
                return False

        return True