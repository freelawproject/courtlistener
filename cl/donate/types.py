from typing import Any, Dict, List, Optional, Union

StripeRefundObject = Dict[
    str,
    Union[
        Optional[str],
        int,
        Dict[str, Any],
    ],
]

StripeChargeObject = Dict[
    str,
    Optional[
        Union[
            str,
            int,
            bool,
            Dict[
                str,
                Union[
                    int,
                    int,
                    bool,
                    List[StripeRefundObject],
                    Optional[str],
                    Dict[str, Optional[str]],
                ],
            ],
        ]
    ],
]

StripeEventObject = Dict[
    str,
    Union[
        bool,
        int,
        str,
        # Charge object
        Dict[
            str,
            StripeChargeObject,
        ],
        # request key
        Dict[str, Union[int, str]],
    ],
]
