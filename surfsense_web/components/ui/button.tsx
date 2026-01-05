import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

// M3 Button Styles
// Default (Filled): Primary bg, OnPrimary text, no shadow initially (elevation 0) -> hover elevation 1
// Secondary (Tonal): SecondaryContainer bg, OnSecondaryContainer text
// Outline: Border outline, transparent bg, Primary text
// Ghost (Text): Transparent bg, Primary text
// Destructive: Error bg, OnError text

const buttonVariants = cva(
	"inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-[color,background-color,box-shadow,opacity] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive overflow-hidden relative",
	{
		variants: {
			variant: {
				default:
					"bg-md-primary text-md-on-primary shadow-none hover:shadow-elevation-1 hover:bg-md-primary/92 active:bg-md-primary/88",
				destructive:
					"bg-md-error text-md-on-error shadow-none hover:shadow-elevation-1 hover:bg-md-error/92 active:bg-md-error/88",
				outline:
					"border border-md-outline bg-transparent text-md-primary shadow-none hover:bg-md-primary/8 active:bg-md-primary/12 focus-visible:bg-md-primary/12",
				secondary:
					"bg-md-secondary-container text-md-on-secondary-container shadow-none hover:shadow-elevation-1 hover:bg-md-secondary-container/92 active:bg-md-secondary-container/88",
				ghost:
					"bg-transparent text-md-primary hover:bg-md-primary/8 active:bg-md-primary/12",
				link: "text-md-primary underline-offset-4 hover:underline",
			},
			size: {
				default: "h-10 px-6 py-2.5", // M3 standard height is 40dp
				sm: "h-8 px-4",
				lg: "h-12 px-8",
				icon: "size-10 rounded-full",
			},
		},
		defaultVariants: {
			variant: "default",
			size: "default",
		},
	}
);

function Button({
	className,
	variant,
	size,
	asChild = false,
	...props
}: React.ComponentProps<"button"> &
	VariantProps<typeof buttonVariants> & {
		asChild?: boolean;
	}) {
	const Comp = asChild ? Slot : "button";

	return (
		<Comp
			data-slot="button"
			className={cn(buttonVariants({ variant, size, className }))}
			{...props}
		/>
	);
}

export { Button, buttonVariants };
