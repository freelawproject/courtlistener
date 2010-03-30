$.fn.collapse = function(options) {
	var defaults = {
		closed : false
	}
	settings = $.extend({}, defaults, options);

	return this.each(function() {
		var obj = $(this);
		obj.find("legend:first").addClass('collapsible').click(function() {
			if (obj.hasClass('collapsed'))
				obj.removeClass('collapsed').addClass('collapsible');
	
			$(this).removeClass('collapsed');
	
			obj.children().not('legend').toggle("slow", function() {
			 
				 if ($(this).is(":visible"))
					obj.find("legend:first").addClass('collapsible');
				 else
					obj.addClass('collapsed').find("legend").addClass('collapsed');
			 });
		});
		if (settings.closed) {
			obj.addClass('collapsed').find("legend:first").addClass('collapsed');
			obj.children().not("legend:first").css('display', 'none');
		}
	});
};

