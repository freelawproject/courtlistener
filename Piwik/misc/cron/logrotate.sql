use piwik;
DELETE 
    piwik_log_visit, piwik_log_link_visit_action
FROM 
    piwik_log_visit INNER JOIN piwik_log_link_visit_action
WHERE 
    piwik_log_visit.idvisit = piwik_log_link_visit_action.idvisit
    AND visit_first_action_time <= DATE_SUB(CURDATE(), INTERVAL 84 DAY);
OPTIMIZE TABLE piwik_log_visit, piwik_log_link_visit_action;
